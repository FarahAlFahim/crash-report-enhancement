# Crash Report Enhancement using LLM

This repository provides data artifacts and Python scripts for enhancing crash reports with large language models (LLMs) and evaluating the enhanced reports.

At a high level, the workflow is:

1. collect and normalize developer-written bug reports and their stack traces,
2. extract relevant Java methods by navigating call dependencies starting from stack traces (at the project revision corresponding to the report timestamp),
3. generate enhanced bug reports using two settings (direct prompting and an agentic, iterative method-inspection procedure),
4. generate candidate repairs as full Java method bodies, and
5. evaluate outputs using method-level fault localization (BM25), CodeBLEU, and an LLM-based judge.

## Repository contents

### `data/`
Inputs and intermediate artifacts used by the pipeline.

**Bug reports and stack traces**
- `data/developer_written_bug_reports/` — developer-written bug reports (per project) in JSON.
- `data/stack_traces/` — stack traces (per project) in JSON.
- `data/stack_traces_and_developer_written_bug_reports/` — merged bug reports and stack traces.

**Source-code extraction output**
- `data/source_code_data/` — for each bug: extracted source-code methods (from the stack-trace call-dependency navigation), along with the bug report and stack trace.

**LLM-generated artifacts**
- `data/direct_llm_bug_reports/` — enhanced bug reports generated via direct prompting.
- `data/agentic_llm_bug_reports/` — enhanced bug reports generated via an agent that iteratively requests and analyzes methods.
- `data/direct_llm_possible_fix_full_code/` — candidate repairs generated from direct enhanced reports (full method bodies).
- `data/agentic_llm_possible_fix_full_code/` — candidate repairs generated from agentic enhanced reports (full method bodies).

**Ground truth**
- `data/ground_truth/code_changes.json` — mapping from issue IDs to commit hashes.
- `data/ground_truth/class_level/` — class-level ground-truth locations.
- `data/ground_truth/method_level/` — method-level ground-truth locations.

### `scripts/`
Executable scripts for dataset construction, generation, and evaluation.

**Data preparation**
- `stack_trace_and_bug_report_merger.py` — merges developer bug reports and stack traces.
- `bug_report_data_collector.py` — utility for collecting bug reports with stack traces from an external dataset folder (e.g., Pathidea_Data).

**Source code extraction**
- `source_code_extractor_from_call_graph.py` — checks out the project at the report timestamp and extracts methods reachable via call-dependency navigation from stack traces.

**Bug report generation**
- `direct_llm_generator.py` — generates enhanced bug reports using single-pass prompting.
- `agentic_llm_generator.py` — generates enhanced bug reports using an agentic, iterative method-inspection procedure.

**Candidate repair generation**
- `direct_llm_possible_fix_code_generator.py` — generates candidate fixes (full method bodies) from direct enhanced reports.
- `agentic_llm_possible_fix_code_generator.py` — generates candidate fixes (full method bodies) from agentic enhanced reports.

**Evaluation**
- `fault_localization_BM25.py` — BM25 baseline for method-level fault localization (Top@N, MRR, MAP).
- `codebleu.py` — CodeBLEU implementation used by the calculator.
- `codebleu_score_calculator.py` — computes CodeBLEU for generated candidate fixes against ground-truth methods.
- `llm_judge.py` — LLM-based evaluation of bug report quality against ground-truth methods and code differences.
- `llm_judgement_category_counter.py` — aggregates and summarizes LLM-judge categories.
- `projectwise_score_calculator.py` — computes project-wise summary metrics from method-level outputs.
- `ground_truth_method_extractor.py` — derives method-level ground truth from commits/diffs given class-level labels.

### `results/`
Outputs produced by running the evaluation scripts.

- `results/method_level/BM25/` — BM25 fault-localization outputs.
- `results/method_level/projectwise_scores/` — project-level summaries derived from method-level outputs.
- `results/codebleu/agentic_llm/`, `results/codebleu/direct_llm/` — CodeBLEU results for generated candidate fixes.
- `results/llm_judge/` — LLM judge outputs for bug reports (developer-written, direct, agentic).
- `results/Method_of_BR_matching_with_grountTruth/` — artifacts for mapping bug reports to ground truth.
- `results/user_study/` — materials and responses used for the user study.

## Data format (high level)

Files in `data/` are JSON lists keyed by `filename` (e.g., `ZOOKEEPER-1864.json`) and typically include:

- `creation_time`: timestamp used to select a project revision (via `git rev-list --before`).
- `stack_trace`: stack trace text.
- `bug_report`: structured JSON object representing the report.
- `source_code` / `analyzed_methods`: mapping from fully qualified method name to method body.
- `possible_fix_code`: mapping from fully qualified method name to a full *fixed* method body.

## Environment and assumptions

- The scripts are written for Python and use common NLP/LLM libraries (e.g., LangChain, `javalang`, `rank_bm25`, NLTK).
- LLM-based scripts require an API key configured in the environment (e.g., `OPENAI_API_KEY`).
- Several scripts expect local clones of the target Java projects under `Projects/` (e.g., `Projects/zookeeper`, `Projects/hadoop`, `Projects/hive`, `Projects/storm`, `Projects/activemq`) and use `git` to checkout revisions.
- The original bug-report JSON files were collected from the Pathidea dataset: https://github.com/SPEAR-SE/Pathidea_Data

## Pipeline overview

1) **Merge bug reports and stack traces**
- Input: `data/developer_written_bug_reports/<Project>.json` and `data/stack_traces/<Project>.json`
- Output: `data/stack_traces_and_developer_written_bug_reports/<Project>.json`

2) **Extract relevant methods from code**
- Input: merged bug reports + stack traces, plus local project clones under `Projects/`
- Output: `data/source_code_data/<Project>.json`

3) **Generate enhanced bug reports**
- Direct: `data/direct_llm_bug_reports/<Project>.json`
- Agentic: `data/agentic_llm_bug_reports/<Project>.json`

4) **Generate candidate repairs (full method bodies)**
- Direct: `data/direct_llm_possible_fix_full_code/<Project>.json`
- Agentic: `data/agentic_llm_possible_fix_full_code/<Project>.json`

5) **Evaluate**
- BM25 method-level fault localization: `results/method_level/BM25/`
- CodeBLEU: `results/codebleu/.../`
- LLM judge: `results/llm_judge/.../`

## Important notes

- Many scripts select the target project and file paths via constants near the bottom of each script.
- Several scripts run `git reset --hard`, `git stash`, and `git checkout` inside the target project directories; run on clean clones.
- LLM-generated outputs are parsed as strict JSON; entries may be skipped if parsing fails.
