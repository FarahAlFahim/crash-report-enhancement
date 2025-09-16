import json

# File paths
stack_trace_file = "data/stack_traces/YARN.json"
bug_report_file = "data/developer_written_bug_reports/YARN.json"
output_file = "data/stack_traces_and_developer_written_bug_reports/YARN.json"

# Load JSON data
with open(stack_trace_file, "r") as f:
    stack_traces = json.load(f)

with open(bug_report_file, "r") as f:
    bug_reports = json.load(f)

# Convert bug reports to a dictionary for easy lookup
bug_report_dict = {item["filename"]: item for item in bug_reports}

# Merge data
merged_data = []
for stack_trace in stack_traces:
    filename = stack_trace["filename"]
    if filename in bug_report_dict:
        merged_entry = {
            "filename": filename,
            "creation_time": stack_trace["creation_time"],
            "stack_trace": stack_trace["stack_trace"],
            "bug_report": bug_report_dict[filename]["bug_report"]
        }
        merged_data.append(merged_entry)

# Save merged data
with open(output_file, "w") as f:
    json.dump(merged_data, f, indent=4)

print(f"Merged data saved to {output_file}")
