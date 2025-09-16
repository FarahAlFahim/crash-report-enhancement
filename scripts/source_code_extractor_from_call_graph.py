import os
import json
import subprocess
import javalang
from collections import defaultdict
from collections import deque


# Step 1: Read Stack Traces from JSON
def read_stack_traces(json_file):
    with open(json_file, "r") as file:
        return json.load(file)

# Step 2: Get the commit version before a specific timestamp
def get_commit_version(creation_time, repo_path, git_branch):
    command = f'git rev-list -n 1 --before="{creation_time}" {git_branch}'
    result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=repo_path)
    return result.stdout.strip()

# Step 3: Checkout to the specific commit version
def checkout_to_commit(commit_version, repo_path, git_branch):
    subprocess.run('git reset --hard', shell=True, cwd=repo_path)
    subprocess.run('git stash push --include-untracked', shell=True, cwd=repo_path)
    subprocess.run(f'git checkout {git_branch}', shell=True, cwd=repo_path)
    subprocess.run('git pull', shell=True, cwd=repo_path)
    subprocess.run(f'git checkout {commit_version}', shell=True, cwd=repo_path)
    subprocess.run('git stash drop', shell=True, cwd=repo_path)

# Step 4: Extract methods and call dependencies from Java source code using javalang
def extract_method_code(file_content, method_position):
    """
    Extract the full method code using the position provided by javalang.
    """
    lines = file_content.splitlines()
    start_line = method_position.line - 1  # javalang position is 1-indexed
    method_lines = []
    open_braces = 0
    found_method_start = False  # To track when the method body starts

    for i in range(start_line, len(lines)):
        line = lines[i]
        method_lines.append(line)

        # Update brace counts
        open_braces += line.count('{')
        open_braces -= line.count('}')

        # Check if we are inside the method body
        if '{' in line and not found_method_start:
            found_method_start = True

        # Stop when all braces are balanced after method body starts
        if found_method_start and open_braces == 0:
            break

    return "\n".join(method_lines)



def resolve_variable_type_with_javalang(variable_name, tree):
    """
    Resolves the class type of a given variable by analyzing the AST with javalang.
    """
    for path, local_var in tree.filter(javalang.tree.LocalVariableDeclaration):
        for declarator in local_var.declarators:
            if declarator.name == variable_name:
                if hasattr(local_var.type, 'name'):
                    return local_var.type.name
    return None



def extract_methods_and_calls(file_path):
    """
    Extracts method declarations and method calls from the provided Java file.
    """
    methods = {}
    call_graph = {}

    try:
        with open(file_path, 'r') as file:
            content = file.read()

        # Parse the Java file with javalang
        tree = javalang.parse.parse(content)
        temp_tree = tree

        for _, method in tree.filter(javalang.tree.MethodDeclaration):
            method_name = method.name
            # parameters = ", ".join(param.type.name for param in method.parameters) if method.parameters else ""
            # method_key = f"{method_name}({parameters})"

            # Remove repo_path from the beginning of file_path
            relative_path = os.path.relpath(file_path, repo_path)
            relative_path = relative_path[:-5]
            formatted_path = relative_path.replace('/', '.') # Replace slashes with dots
            method_key = f"{formatted_path}.{method_name}"

            # Extract full method code using the position of the method
            method_code = extract_method_code(content, method.position)
            methods[method_key] = method_code

            # Add method calls to call graph
            for _, call in method.filter(javalang.tree.MethodInvocation):
                qualifier_name = call.qualifier
                if qualifier_name and qualifier_name[0].islower():  # Object detected
                    actual_class_name = resolve_variable_type_with_javalang(qualifier_name, temp_tree)
                    # print("actual_class_name:", actual_class_name)
                    if actual_class_name:
                        qualifier_name = actual_class_name
                    # print("qualifier_name:", qualifier_name)
                call_graph.setdefault(method_key, []).append(f'{qualifier_name}.{call.member}')
                # print(f'call.member: {qualifier_name}.{call.member}')

            # print(f"Extracted Method: {method_key} in {file_path}")

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
    # print("methods:", methods)
    # print("call_graph:", call_graph)
    return methods, call_graph



# Step 5: Parse stack trace to locate methods
def parse_stack_trace(stack_trace, codebase_dirs):
    method_files = {}
    
    for line in stack_trace.split("\n"):
        line = line.strip()
        
        # Ignore empty lines and ensure it starts with 'at '
        if not line.startswith("at "):
            continue

        # Remove 'at ' prefix
        line = line[3:]  

        # parts = line.split("(")
        # if len(parts) < 2:
        #     continue

        parts = line.split("(", 1)  # Only split on the first "("
        if len(parts) != 2:
            continue
        
        class_method_part, file_part = parts
        file_name = file_part.split(":")[0] if ":" in file_part else None
        if not file_name:
            continue
        
        # Extract class name and method
        method_parts = class_method_part.split(".")
        if len(method_parts) < 2:
            continue
        
        class_name = ".".join(method_parts[:-1])  # Full class name (package + class)
        method_name = method_parts[-1]  # Method name
        
        # Extract just the filename without path details
        file_name = os.path.basename(file_name)

        # Search for the correct file in `codebase_dirs`
        found = False
        for codebase_dir in codebase_dirs:
            for root, _, files in os.walk(codebase_dir):
                if file_name in files:
                    full_path = os.path.join(root, file_name)
                    print(f"Corrected Path: {full_path}")  # Debugging
                    method_files[(method_name, class_name)] = full_path
                    found = True
                    break
            if found:
                break
        
        if not found:
            print(f"File not found: {file_name} (Original class: {class_name})")  # Debugging

    return method_files


# Step 6: Navigate code using the call graph
def navigate_code(stack_trace, codebase_dirs):
    method_files = parse_stack_trace(stack_trace, codebase_dirs)
    # print("method_files:", method_files)
    visited_methods = set()
    extracted_methods = {}
    call_graph = defaultdict(list)

    # Step 1: Initialize priority queue with stack trace methods
    priority_list = deque([(method_name, class_name) for (method_name, class_name) in method_files.keys()])

    while priority_list:
        # print("priority_list:", priority_list)
        method_name, class_name = priority_list.popleft()  # Process the next method


        # Get the file path where this method is defined
        file_path = method_files.get((method_name, class_name))
        if not file_path or not os.path.exists(file_path):
            continue  # Skip if file doesn't exist

        # Step 2: Extract methods and call relationships
        methods, calls = extract_methods_and_calls(file_path)
        # print("methods:", methods)
        # print("calls:", calls)
        call_graph.update(calls)

        # Normalize method name to match extracted method format
        method_key = None
        for key in methods.keys():
            if key.endswith(f".{method_name}"):  # Match method name with extracted method key
                method_key = key
                break

        if not method_key or method_key in visited_methods:
            continue

        # Step 3: Store extracted method and mark as visited
        extracted_methods[method_key] = methods[method_key]
        visited_methods.add(method_key)

        # Step 4: Add all reachable methods to priority list if not visited
        if method_key in call_graph:
            # print("method_key:", method_key)
            # print('methods.keys():', methods.keys())
            for called_method in set(call_graph[method_key]):  # Ensure unique method names
                # print("called_method:", called_method)
                # print("set(call_graph[method_key]):", set(call_graph[method_key]))
                # Find the full qualified name of the called method
                called_class_name = called_method.split(".")[0]
                called_method_name = called_method.split(".")[1]
                called_method_key = None
                for extracted_key in methods.keys():
                    if extracted_key.endswith(f".{called_method_name}"):
                        called_method_key = extracted_key
                        break

                # Search for `called_class.java` in `codebase_dirs`
                if not called_method_key:
                    package_name = "/".join(class_name.split(".")[:-1]) 
                    called_file_path = None
                    for directory in codebase_dirs:
                        possible_path = os.path.join(directory, package_name, f"{called_class_name}.java")
                        # print("possible_path:", possible_path)
                        if os.path.exists(possible_path):
                            called_file_path = possible_path
                            # print("called_file_path:", called_file_path)
                            called_full_class_name = f'{package_name+called_class_name}'
                            method_files_key = (called_method_name, called_full_class_name)
                            method_files[method_files_key] = called_file_path
                            # print("new method_files:", method_files)
                            # Add to queue
                            priority_list.append((called_method_name, called_full_class_name))
                            break

                if not called_method_key or called_method_key in visited_methods:
                    continue  # Skip if already processed
                
                # print("class_name:", class_name)
                priority_list.append((called_method_name, class_name))  # Add to queue
                visited_methods.add(called_method_key)  # Mark as visited immediately
                extracted_methods[called_method_key] = methods[called_method_key]  # Store method

    # print(f"call_graph: {call_graph}")
    # print(f"Final Extracted Methods: {list(extracted_methods.keys())}")
    return extracted_methods



# Step 7: Merge with developer written bug reports
def merge_bug_reports(output_data, bug_reports_file):
    """
    Merge developer-written bug reports into the output data.
    Checks if 'filename' and 'creation_time' match and adds the 'bug_report' field if found.
    """
    with open(bug_reports_file, "r") as file:
        developer_bug_reports = json.load(file)

    # Create a lookup for developer bug reports based on filename and creation_time
    bug_report_lookup = {
        (entry["filename"], entry["creation_time"]): entry["bug_report"]
        for entry in developer_bug_reports
    }

    # Add 'bug_report' to the output data if there is a match
    for output_entry in output_data:
        key = (output_entry["filename"], output_entry["creation_time"])
        if key in bug_report_lookup:
            output_entry["bug_report"] = bug_report_lookup[key]

    print("Bug reports have been merged into the output data.")
    return output_data


# Step 7: Main Execution
if __name__ == "__main__":
    # stack_trace_file = "test.json"
    stack_trace_file = "data/stack_traces/Storm.json"
    stack_trace_data = read_stack_traces(stack_trace_file)

    # For Storm.json
    repo_path = "Projects/storm"
    codebase_dirs = ['Projects/storm/examples/storm-loadgen/src/main/java', 'Projects/storm/external/storm-hdfs-blobstore/src/main/java', 'Projects/storm/external/storm-hdfs/src/main/java', 'Projects/storm/external/storm-kafka-client/src/main/java', 'Projects/storm/storm-client/src/jvm', 'Projects/storm/storm-core/src/jvm', 'Projects/storm/storm-server/src/main/java', 'Projects/storm/storm-webapp/src/main/java']
    git_branch = "master"
    # Path to developer-written bug reports
    dev_written_bug_reports_file = "data/developer_written_bug_reports/Storm.json"

    # Prepare output
    output_data = []

    for entry in stack_trace_data:
        filename = entry['filename']
        creation_time = entry['creation_time']
        stack_trace = entry['stack_trace']

        commit_version = get_commit_version(creation_time, repo_path, git_branch)
        checkout_to_commit(commit_version, repo_path, git_branch)

        relevant_methods = navigate_code(stack_trace, codebase_dirs)

        # print("Extracted Methods:", relevant_methods.keys())


        # Add to output data
        output_data.append({
            'filename': filename,
            'creation_time': creation_time,
            'stack_trace': stack_trace,
            'source_code': relevant_methods
        })

    # Merge developer-written bug reports into the output data
    output_data = merge_bug_reports(output_data, dev_written_bug_reports_file)

    # Write output to JSON
    # output_file = 'test_output.json'
    output_file = 'data/source_code_data/Storm.json'
    with open(f"{output_file}", "w") as outfile:
        json.dump(output_data, outfile, indent=4)

    print(f"Source code have been extracted and saved to '{output_file}'")
