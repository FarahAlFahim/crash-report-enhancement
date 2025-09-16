# prompt templating and chaining
from langchain import PromptTemplate
from langchain_core.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.chains import LLMChain
import json




# template
template = '''
You are a **professional bug fixing assistant**.  
Your task is to propose a **possible fix in code** for the given bug using the provided inputs.

### **Inputs**  
1. **Agent-Based Bug Report**: Agent-Based Bug Report containing stack traces.  
2. **Agent-Based Chat History**: Conversation log where an agent analyzes source code methods related to the bug.  
3. **Source Code Methods**: Methods analyzed by the agent that appear in stack traces or are part of the call dependency graph of those methods.  

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





# You are given the **Agent-Based Bug Report** below:

{bug_report}



# You are given the **Agent-Based Chat History** below:

{chat_history}



# You are given the **Source Code Methods** below:

{analyzed_methods}
'''




prompt = PromptTemplate.from_template(template)
llm = ChatOpenAI(model='gpt-4o-mini', temperature = 0)

chain = LLMChain(llm=llm, prompt=prompt)



# File paths
agent_based_file = "data/agentic_llm_bug_reports/Zookeeper.json"
fallback_source_file = "data/source_code_data/Zookeeper.json"
output_file = "data/agentic_llm_possible_fix_full_code/Zookeeper.json"


# Load JSON data from a file
def load_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
    
def all_methods_missing(analyzed_methods: dict) -> bool:
    """Check if all analyzed_methods are '[Method not found in codebase]'."""
    return all(v == "[Method not found in codebase]" for v in analyzed_methods.values())
    

# Load the JSON files
agent_based_data = load_json(agent_based_file)
fallback_data = load_json(fallback_source_file)

# Create a mapping from filename to bug_report for modified_dev_data
fallback_map = {item["filename"]: item.get("source_code", {}) for item in fallback_data}

# Prepare the output format
output_data = []

for entry in agent_based_data:
    filename = entry['filename']
    creation_time = entry['creation_time']
    analyzed_methods = entry['analyzed_methods']
    class_skeleton_cache = entry['class_skeleton_cache']
    chat_history = entry['chat_history']
    bug_report = entry["bug_report"]

    # Fallback handling
    if all_methods_missing(analyzed_methods):
        # replace with fallback source_code (if available)
        # print('No Methods found!')
        analyzed_methods = fallback_map.get(filename, {})
    
    # Generate improved bug report
    fix_code_str = chain.run({'bug_report': bug_report, 'chat_history': chat_history, 'analyzed_methods': analyzed_methods})
    


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
        # "analyzed_methods": analyzed_methods,
        # "class_skeleton_cache": class_skeleton_cache,
        # "chat_history": chat_history,
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