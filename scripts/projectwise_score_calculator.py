import json

def match_ranked_to_ground_truth(ranked_file, ground_truth_files):
    for ground_truth_file in ground_truth_files:
        if ground_truth_file.endswith(ranked_file):
            return True
    return False

def evaluate_metrics(results, ground_truth, top_n_values):
    """
    results: list of (filename, ranked_methods)
    ground_truth: dict filename -> ground_truth list
    returns metrics with:
      - MAP: list of AP per report
      - MRR: list of reciprocal ranks (one per report when found)
      - Top@N: counts of reports with >=1 hit inside top N
      - total_reports: number of evaluated reports
    """
    metrics = {"MAP": [], "MRR": [], "Top@N": {n: 0 for n in top_n_values}, "total_reports": 0}

    for filename, ranked_methods in results:
        ground_truth_files = ground_truth.get(filename, [])
        if not ground_truth_files:
            continue

        metrics["total_reports"] += 1
        relevant_found = 0
        precision_sum = 0.0
        relevant_within_top_n = {n: False for n in top_n_values}

        for rank, file in enumerate(ranked_methods, start=1):
            if match_ranked_to_ground_truth(file, ground_truth_files):
                relevant_found += 1
                precision_sum += relevant_found / rank
                if relevant_found == 1:
                    metrics["MRR"].append(1.0 / rank)
                for n in top_n_values:
                    if rank <= n and not relevant_within_top_n[n]:
                        metrics["Top@N"][n] += 1
                        relevant_within_top_n[n] = True

        avg_precision = precision_sum / relevant_found if relevant_found > 0 else 0.0
        metrics["MAP"].append(avg_precision)

    return metrics

def aggregate_results(results_list, top_n_values):
    """
    results_list: list of metrics objects returned by evaluate_metrics
    returns aggregated metrics:
      - MAP: mean AP across reports
      - MRR: mean reciprocal rank across reports
      - Top@N: for each n -> {"fraction": fraction, "count": count}
      - total_cases: total number of evaluated reports summed across results_list
    """
    total_reports = sum(result["total_reports"] for result in results_list)
    overall_metrics = {
        "MAP": 0.0,
        "MRR": 0.0,
        "Top@N": {n: {"fraction": 0.0, "count": 0} for n in top_n_values},
        "total_cases": total_reports
    }

    if total_reports == 0:
        return overall_metrics

    # accumulate
    for result in results_list:
        if result["MAP"]:
            overall_metrics["MAP"] += (sum(result["MAP"]) / len(result["MAP"])) * result["total_reports"]
        if result["MRR"]:
            overall_metrics["MRR"] += (sum(result["MRR"]) / len(result["MRR"])) * result["total_reports"]
        for n in top_n_values:
            overall_metrics["Top@N"][n]["count"] += result["Top@N"].get(n, 0)

    # normalize to fractions
    overall_metrics["MAP"] /= total_reports
    overall_metrics["MRR"] /= total_reports
    for n in top_n_values:
        overall_metrics["Top@N"][n]["fraction"] = overall_metrics["Top@N"][n]["count"] / total_reports

    return overall_metrics

def process_file(file_path, project_list, top_n_values):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    # If last entry looks like overall-summary (has key 'overall_metrics'), pop it
    overall_results = {}
    if data and isinstance(data[-1], dict) and "overall_metrics" in data[-1]:
        overall_results = data.pop()  # remove from list, but keep for final output

    project_results = {project: [] for project in project_list}
    project_ground_truth = {project: {} for project in project_list}

    for entry in data:
        filename = entry.get("filename")
        if not filename:
            # skip entries that do not look like regular report entries
            continue

        for project in project_list:
            if project.lower() in filename.lower():
                # allow two possible keys (methods vs files) as fallback
                ranked_files = entry.get("transformed_ranked_methods", entry.get("transformed_ranked_files", []))
                ground_truth = entry.get("ground_truth", [])
                project_results[project].append((filename, ranked_files))
                project_ground_truth[project][filename] = ground_truth

    project_metrics = {}
    overall_total_cases = 0

    for project in project_list:
        metrics = evaluate_metrics(project_results[project], project_ground_truth[project], top_n_values)
        aggregated_metrics = aggregate_results([metrics], top_n_values)
        project_metrics[project] = aggregated_metrics
        overall_total_cases += aggregated_metrics["total_cases"]

    # attach total_cases to overall_results (if we popped it earlier, keep original fields and add total_cases)
    if overall_results:
        overall_results["total_cases"] = overall_total_cases
    else:
        # if there was no original overall item, create a basic one from aggregated project metrics
        # combine all projects' aggregated metrics to produce an "overall" summary
        combined = aggregate_results([project_metrics[p] for p in project_list], top_n_values)
        overall_results = {
            "overall_metrics": {
                "MAP": combined["MAP"],
                "MRR": combined["MRR"],
                "Top@N": {str(n): combined["Top@N"][n]["fraction"] for n in top_n_values}
            },
            "top@N_value_counts": {f"Top-{n}": combined["Top@N"][n]["count"] for n in top_n_values},
            "total_cases": combined["total_cases"]
        }

    return project_metrics, overall_results

if __name__ == "__main__":
    project_list = ['ZOOKEEPER', 'AMQ', 'HADOOP', 'HDFS', 'HIVE', 'MAPREDUCE', 'STORM', 'YARN']
    top_n_values = [1, 3, 5, 10]

    bug_report_folder = 'developer_written_bug_reports'
    input_file = f"results/method_level/BM25/{bug_report_folder}.json"
    output_file = f"results/method_level/BM25/projectwise_scores/{bug_report_folder}.json"

    project_results, overall_results = process_file(input_file, project_list, top_n_values)

    # Format final output so Top@N shows both fraction and count per project
    formatted_project_metrics = {}
    for project, metrics in project_results.items():
        formatted_project_metrics[project] = {
            "MAP": metrics["MAP"],
            "MRR": metrics["MRR"],
            "Top@N": {str(n): {"fraction": metrics["Top@N"][n]["fraction"], "count": metrics["Top@N"][n]["count"]} for n in top_n_values},
            "total_cases": metrics["total_cases"]
        }

    # Format overall_results: if it came from file, keep original shape but add per-n counts if available
    if "overall_metrics" in overall_results and "top@N_value_counts" in overall_results:
        # preserve original and add counts object for convenience
        overall_counts = overall_results.get("top@N_value_counts", {})
        overall_metrics_obj = overall_results["overall_metrics"]
        overall_formatted = {
            "overall_metrics": overall_metrics_obj,
            "top@N_value_counts": overall_counts,
            "total_cases": overall_results.get("total_cases", 0)
        }
    else:
        # we created overall_results above in process_file
        overall_formatted = overall_results

    final_output = {**formatted_project_metrics, "Overall": overall_formatted}

    with open(output_file, "w", encoding="utf-8") as out_file:
        json.dump(final_output, out_file, indent=4)

    print(f"Metrics saved to {output_file}")




