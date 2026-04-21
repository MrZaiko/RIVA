"""Naive ReAct client for AIOpsLab.

Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2022).
React: Synergizing reasoning and acting in language models. arXiv preprint arXiv:2210.03629.

Code: https://github.com/ysymyth/ReAct
Paper: https://arxiv.org/abs/2210.03629
"""

import argparse
import asyncio
import json
import os

import tiktoken

import wandb
from aiopslab.orchestrator import Orchestrator
from aiopslab.orchestrator.actions.base import MAX_TOOLS_PER_GOAL, tool_history
from aiopslab.orchestrator.problems.registry import ProblemRegistry
from clients.utils.llm import GPTClient
from clients.utils.riva_prompts import GENERATOR_DOCS, VERIFIER_DOCS
from clients.utils.templates import DOCS

RESP_INSTR = """DO NOT REPEAT ACTIONS! Respond with:
Thought: <your thought on the previous output>
Action: <your action towards mitigating>
"""


def count_message_tokens(message, enc):
    # Each message format adds ~4 tokens of overhead
    tokens = 4  # <|start|>role/name + content + <|end|>
    tokens += len(enc.encode(message.get("content", "")))
    return tokens


def trim_history_to_token_limit(history, max_tokens=120000, model="gpt-4"):
    enc = tiktoken.encoding_for_model(model)

    trimmed = []
    total_tokens = 0

    # Always include the last message
    last_msg = history[-1]
    last_msg_tokens = count_message_tokens(last_msg, enc)

    if last_msg_tokens > max_tokens:
        # If even the last message is too big, truncate its content
        truncated_content = enc.decode(
            enc.encode(last_msg["content"])[: max_tokens - 4]
        )
        return [{"role": last_msg["role"], "content": truncated_content}]

    trimmed.insert(0, last_msg)
    total_tokens += last_msg_tokens

    # Add earlier messages in reverse until limit is reached
    for message in reversed(history[:-1]):
        message_tokens = count_message_tokens(message, enc)
        if total_tokens + message_tokens > max_tokens:
            break
        trimmed.insert(0, message)
        total_tokens += message_tokens

    return trimmed


class Agent:
    def __init__(self):
        self.history = []
        self.llm = GPTClient()

    def init_context(self, problem_desc: str, instructions: str, apis: str):
        """Initialize the context for the agent."""

        self.shell_api = self._filter_dict(apis, lambda k, _: "exec_shell" in k)
        self.submit_api = self._filter_dict(
            apis, lambda k, _: "submit" in k and "submit_" not in k
        )
        self.telemetry_apis = self._filter_dict(
            apis,
            lambda k, _: (
                "exec_shell" not in k
                and "submit" not in k
                and "goal" not in k
                and "ask_generator" not in k
            ),
        )

        stringify_apis = lambda apis: "\n\n".join(
            [f"{k}\n{v}" for k, v in apis.items()]
        )

        self.system_message = DOCS.format(
            prob_desc=problem_desc,
            k=MAX_TOOLS_PER_GOAL,
            telemetry_apis=stringify_apis(self.telemetry_apis),
            shell_api=stringify_apis(self.shell_api),
            submit_api=stringify_apis(self.submit_api),
        )

        self.task_message = instructions

        self.history.append({"role": "system", "content": self.system_message})
        self.history.append({"role": "user", "content": self.task_message})

    def get_extra_details(self):
        extra_details = {"full_prompt": self.llm.get_extra_details()}

        self.llm.clear_history()

        return extra_details

    async def get_action(self, input) -> str:
        """Wrapper to interface the agent with OpsBench.

        Args:
            input (str): The input from the orchestrator/environment.

        Returns:
            str: The response from the agent.
        """
        self.history.append({"role": "user", "content": self._add_instr(input)})
        trimmed_history = trim_history_to_token_limit(self.history)
        response = self.llm.run(trimmed_history)
        self.history.append({"role": "assistant", "content": response[0]})
        return response[0]

    def _filter_dict(self, dictionary, filter_func):
        return {k: v for k, v in dictionary.items() if filter_func(k, v)}

    def _add_instr(self, input):
        return input + "\n\n" + RESP_INSTR


def stringify_apis(apis):
    return "\n\n".join([f"{k}\n{v}" for k, v in apis.items()])


class RIVAAgent:
    verifier_system_prompt: str
    generator_system_prompt: str

    def __init__(self):
        self.verifier_history = []
        self.generator_history = []
        self.generator_in_use = False
        self.transitionning = False

        self.llm = GPTClient()

    def init_context(self, problem_desc: str, instructions: str, apis: str):
        """Initialize the context for the agent."""

        self.problem_desc = problem_desc
        self.shell_api = self._filter_dict(apis, lambda k, _: "exec_shell" in k)
        self.submit_api = self._filter_dict(apis, lambda k, _: "submit" in k)
        self.history_api = self._filter_dict(apis, lambda k, _: "goal" in k)
        self.verifier_ask_api = self._filter_dict(
            apis, lambda k, _: "ask_generator" in k
        )
        self.generator_submit_api = self._filter_dict(
            apis, lambda k, _: "submit_generated_tool" in k
        )
        self.telemetry_apis = self._filter_dict(
            apis,
            lambda k, _: (
                "exec_shell" not in k
                and "submit" not in k
                and "ask_generator" not in k
                and "goal" not in k
            ),
        )

        self.verifier_system_prompt = VERIFIER_DOCS.format(
            prob_desc=problem_desc,
            k=MAX_TOOLS_PER_GOAL,
            tool_history_api=stringify_apis(self.history_api),
            generate_command_api=stringify_apis(self.verifier_ask_api),
            submit_api=stringify_apis(self.submit_api),
        )

        self.task_message = instructions
        self.verifier_history.append(
            {"role": "system", "content": self.verifier_system_prompt}
        )
        self.verifier_history.append({"role": "user", "content": self.task_message})

        self.reset_and_prepare_generator("", "")
        self.generator_in_use = False
        self.transitionning = False

    def reset_and_prepare_generator(self, tool_history, task):
        self.generator_history = []
        self.generator_system_prompt = GENERATOR_DOCS.format(
            tool_history=tool_history,
            telemetry_apis=stringify_apis(self.telemetry_apis),
            shell_api=stringify_apis(self.shell_api),
            generator_submit_api=stringify_apis(self.generator_submit_api),
        )

        self.generator_history.append(
            {"role": "system", "content": self.generator_system_prompt}
        )
        self.generator_history.append(
            {
                "role": "user",
                "content": """\
                You will respond with one of the above APIs as your next action.
                Please respond in the following format in a markdown code block:
                ```\n<API_NAME>(<API_PARAM1>, <API_PARAM2> ...)\n```

                For instance, if you want to list files in current directory, your response must be exactly:

                ```\nexec_shell("ls -l")\n```

                Please respond with only a single API call (a.k.a., action) per turn without any additional words, labels, or prefixes.""",
            }
        )
        self.generator_history.append({"role": "user", "content": task})

    def get_extra_details(self):
        extra_details = {"full_prompt": self.llm.get_extra_details()}

        self.llm.clear_history()

        return extra_details

    async def get_action(self, input) -> str:
        """Wrapper to interface the agent with OpsBench.

        Args:
            input (str): The input from the orchestrator/environment.

        Returns:
            str: The response from the agent.
        """

        if self.transitionning:
            if self.generator_in_use:
                self.verifier_history.append(
                    {"role": "user", "content": self._add_instr(input)}
                )
                trimmed_history = trim_history_to_token_limit(self.verifier_history)

                self.generator_in_use = False
            else:
                history, task = input.split("---")
                self.reset_and_prepare_generator(history, task)
                self.generator_history.append(
                    {"role": "user", "content": self._add_instr(task)}
                )
                trimmed_history = trim_history_to_token_limit(self.generator_history)

                self.generator_in_use = True

            self.transitionning = False

        else:
            if self.generator_in_use:
                self.generator_history.append(
                    {"role": "user", "content": self._add_instr(input)}
                )
                trimmed_history = trim_history_to_token_limit(self.generator_history)
            else:
                self.verifier_history.append(
                    {"role": "user", "content": self._add_instr(input)}
                )
                trimmed_history = trim_history_to_token_limit(self.verifier_history)

        response = self.llm.run(trimmed_history)

        if response[0] is None:
            response[0] = ""

        print("INPUT: " + f"{input}")
        print("RESPONSE: " + f"{response}")

        if self.generator_in_use:
            self.generator_history.append({"role": "assistant", "content": response[0]})

            if "submit_generated_tool" in response[0]:
                self.transitionning = True
        else:
            self.verifier_history.append({"role": "assistant", "content": response[0]})

            if "ask_generator" in response[0]:
                self.transitionning = True

        return response[0]

    def _filter_dict(self, dictionary, filter_func):
        return {k: v for k, v in dictionary.items() if filter_func(k, v)}

    def _add_instr(self, input):
        return input + "\n\n" + RESP_INSTR


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOpsLab")
    parser.add_argument("--resume-id", type=str, default=None, help="Resume ID")
    parser.add_argument("--start-idx", type=int, default=0, help="Start index")
    parser.add_argument("--end-idx", type=int, default=-1, help="Stop index")
    parser.add_argument(
        "--k", type=int, default=MAX_TOOLS_PER_GOAL, help="Max tools per goal"
    )
    parser.add_argument(
        "--invalid-actions",
        type=str,
        nargs="+",
        default=[],
        help="invalid actions",
    )
    args = parser.parse_args()

    MAX_TOOLS_PER_GOAL = args.k

    problems = ProblemRegistry().PROBLEM_REGISTRY
    if args.end_idx == -1:
        args.end_idx = len(problems)

    # Load use_wandb from environment variable with a default of False
    use_wandb = os.getenv("USE_WANDB", "false").lower() == "true"

    # Initialize wandb running
    if use_wandb:
        if args.resume_id is not None:
            app = wandb.init(
                project="AIOpsLab",
                entity="your-wandb-entity",
                id=args.resume_id,
                resume="allow",
            )

        else:
            app = wandb.init(project="AIOpsLab", entity="your-wandb-entity")

    for idx, pid in enumerate(problems):
        if "mitigation" in pid:
            continue

        if idx < args.start_idx:
            continue

        if idx >= args.end_idx:
            break

        actions: list[list[str]] = [[]]
        for action in args.invalid_actions:
            actions.append([action])

        for a in actions:
            tool_history = {}

            for i in range(2):
                orchestrator = Orchestrator()

                if i == 0:
                    agent = Agent()
                    orchestrator.register_agent(agent, name="react")

                else:
                    agent = RIVAAgent()
                    orchestrator.register_agent(agent, name="riva")

                try:
                    problem_desc, instructs, apis = orchestrator.init_problem(
                        pid, incorrect_actions=a
                    )

                    agent.init_context(problem_desc, instructs, apis)

                    full_output = asyncio.run(orchestrator.start_problem(max_steps=45))

                    print("Full output:")
                    print(full_output.keys())

                    session_dict = full_output["session"]
                    print("Session")
                    print(session_dict.keys())

                    result_dict = session_dict["results"]
                    print("Results")
                    print(result_dict.keys())

                    filename = f"runs/{'react' if i == 0 else 'riva'}_{pid}_{a}.json"
                    with open(filename, "w") as f:
                        json.dump(result_dict, f, indent=2)

                    if "localization" in session_dict["problem_id"].lower():
                        session_dict["task_accuracy"] = (
                            "Correct"
                            if result_dict["Localization Accuracy"] == 100
                            else "Incorrect"
                        )
                        session_dict["type"] = "localization"

                    elif "detection" in session_dict["problem_id"].lower():
                        session_dict["task_accuracy"] = (
                            "Correct"
                            if result_dict["Detection Accuracy"] == "Correct"
                            else "Incorrect"
                        )
                        session_dict["type"] = "detection"

                    elif "analysis" in session_dict["problem_id"].lower():
                        session_dict["task_accuracy"] = (
                            "Correct"
                            if result_dict["fault_type_correct"] is True
                            else "Incorrect"
                        )
                        session_dict["type"] = "analysis"

                    session_dict["incorrect_tool"] = "none" if len(a) == 0 else f"{a}"
                    session_dict["k"] = MAX_TOOLS_PER_GOAL
                    session_dict["agent_type"] = "riva" if i == 1 else "react"

                    wandb.log(session_dict)

                except Exception as e:
                    import traceback

                    print(f"Error while running problem {pid}: {e}")
                    traceback.print_exc()

    if use_wandb:
        app.alert(title="Run Completed", text="All problems have been run.")
        wandb.finish()
