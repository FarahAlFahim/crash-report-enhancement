# prompt templating and chaining
from langchain import PromptTemplate
from langchain_core.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.chains import LLMChain
import json
import re
import os


template = '''
You are a **professional bug fixing assistant**.  
Your task is to propose a **possible fix in code** for the given bug using the provided inputs.

### **Inputs**  
1. **Enhanced Bug Report**: An LLM-enhanced bug report containing stack traces.  
2. **Source Code Methods**: Full method bodies that appear in the stack traces.  

### **Guidelines for Fixing**  
- Always produce the **entire fixed method body** (not just a patch snippet).
- Ensure your fix is consistent with Java syntax and can compile without missing braces or imports.  
- Do not invent unrelated methods or files; limit yourself to the provided context.  
- If you are unsure about missing details, make the **minimal plausible fix**.


### **Output Format**  
The output should be structured in **valid JSON** as follows:  

```json
{{
    "possible_fix_code": {{
        "<full method name>": "<The full fixed code here>"
    }}
}}





# You are given the **Enhanced Bug Report** below:

{bug_report}



# You are given the **Source Code Methods** below:

{source_code_methods}
'''




prompt = PromptTemplate.from_template(template)
llm = ChatOpenAI(model='gpt-4o-mini', temperature = 0)

chain = LLMChain(llm=llm, prompt=prompt)



# File paths
non_agent_based_file = "data/direct_llm_bug_reports/Zookeeper.json"
fallback_source_file = "data/source_code_data/Zookeeper.json"
output_file = "data/direct_llm_possible_fix_full_code/Zookeeper.json"


# Load JSON data from a file
def load_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
    
def extract_full_method_paths(stack_trace: str):
    """
    Extracts fully qualified method paths from a stack trace.
    Example: 'org.apache.zookeeper.server.quorum.QuorumPeer.setQuorumVerifier'
    """
    pattern = re.compile(r'((?:[a-zA-Z_][\w$]*\.)+[A-Z][\w$]*\.[a-zA-Z_][\w$]*)\s*\(.*?\)')
    return set(match.strip() for match in pattern.findall(stack_trace))


def filter_source_code_by_full_paths(source_code_dict, full_paths):
    filtered_dict = {}
    for method_path in full_paths:
        for key in source_code_dict:
            if key.endswith(method_path):
                filtered_dict[key] = source_code_dict[key]
    return filtered_dict
    

# Load the JSON files
non_agent_based_data = load_json(non_agent_based_file)
fallback_data = load_json(fallback_source_file)

# create mapping for quick lookup (filename -> source_code dict and filename -> stack trace)
source_code_map = {item["filename"]: item.get("source_code", {}) for item in fallback_data}
stack_trace_map = {item["filename"]: item.get("stack_trace", {}) for item in fallback_data}

# Prepare the output format
output_data = []

for entry in non_agent_based_data:
    filename = entry['filename']
    creation_time = entry['creation_time']
    bug_report = entry["bug_report"]

    # lookup maps
    source_code = source_code_map.get(filename, {})
    stack_trace = stack_trace_map.get(filename, "")


    # Extract method paths from stack trace
    method_paths = extract_full_method_paths(stack_trace)

    # Filter source code dictionary using endswith matching
    source_code_methods = filter_source_code_by_full_paths(source_code, method_paths)


    
    # Generate improved bug report
    fix_code_str = chain.run({'bug_report': bug_report, 'source_code_methods': source_code_methods})
    print("--------------------------------------------------------------------")
    print(fix_code_str)
    print("--------------------------------------------------------------------")


    # Parse the bug report JSON from the generated string
    try:
        # Remove any markdown-style code block indicators (` ```json `) if present
        fix_code_json = json.loads(fix_code_str.replace("```json\n", "").replace("\n```", ""))
    except json.JSONDecodeError:
        print(f"Failed to parse JSON for filename: {filename}")
        continue  # Skip this entry if JSON parsing fails

    
    # Add to output data
    output_data.append({
        'filename': filename,
        'creation_time': creation_time,
        # 'source_code': source_code,
        # "source_code_methods": source_code_methods,
        'bug_report': bug_report,
        "possible_fix_code": fix_code_json.get("possible_fix_code")
    })

    # Write to output file after each bug report
    with open(output_file, "w") as outfile:
        json.dump(output_data, outfile, indent=4)
    print(f"Progress saved to {output_file}")


# # Write the summarized bug reports to a new JSON file
# with open(f"{output_file}", "w") as outfile:
#     json.dump(output_data, outfile, indent=4)

print(f"Bug reports have been generated and saved to '{output_file}'")  