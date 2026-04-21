# RIVA: Leveraging LLM Agents for Reliable Configuration Drift Detection

This folder contains the modifications made to [AIOpsLab](https://github.com/microsoft/AIOpsLab) for the paper:

> **RIVA: Leveraging LLM Agents for Reliable Configuration Drift Detection**
> [arXiv:2603.02345](https://arxiv.org/abs/2603.02345)

## Overview

RIVA (Robust Infrastructure by Verification Agents) is a multi-agent system for detecting configuration drift in cloud-native environments. It uses a **verifier agent** and a **tool generation agent** that collaborate through cross-validation and tool call history tracking to reliably detect configuration drift, even when tool outputs are unreliable.

## Repository Structure

- `modifications.patch` — Full diff of changes (`git diff main...experiments`)
- `run_experiments.sh` — Script to set up a Kind cluster and run experiments
- `clients/` — Agent client implementations (RIVA client, ReAct baseline, GPT baseline)
- `clients/utils/` — Shared utilities (LLM interface, RIVA prompts, templates)
- `aiopslab/` — Modified AIOpsLab framework components (orchestrator, session, services)
- `tests/` — Test files

## Reproducing Results

### Option A: Apply the patch

```bash
# Clone AIOpsLab
git clone https://github.com/microsoft/AIOpsLab.git
cd AIOpsLab

# Apply modifications
git apply riva/modifications.patch
```

### Option B: Manual setup

Copy the files from this folder into the corresponding locations in the AIOpsLab repository, preserving the directory structure.

### Running Experiments

1. Copy `.env.example` to `.env` and fill in your API keys.

2. Run experiments:
   ```bash
   ./run_experiments.sh <kubeconfig> <model> [invalid_actions...]
   ```

   **Arguments:**
   - `<kubeconfig>` — Path to your Kubernetes config file
   - `<model>` — LLM model to use (e.g., `gpt-4o`)
   - `[invalid_actions...]` — Optional list of invalid/bugged action types to inject

   **Examples:**
   ```bash
   # Run with default (correct) actions
   ./run_experiments.sh ~/.kube/config gpt-4o

   # Run with invalid detection and localization actions
   ./run_experiments.sh ~/.kube/config gpt-4o detection localization
   ```
