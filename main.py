import subprocess
import sys
import tempfile
import os
import difflib
import json
import requests


# Openrouter API Key
OPENROUTER_API_KEY = "YOUR_API_KEY"


def run_spectral(api_spec_file, ruleset_file):
    """
    Run Spectral on the given API spec file using the specified ruleset
    """
    try:
        result = subprocess.run(
            [
                "spectral", "lint", api_spec_file,
                "--ruleset", ruleset_file,
                "--fail-severity", "error"
            ],
            capture_output=True,
            text=True,
            check=False
        )
        
        filtered_stdout = "\n".join(
            line for line in result.stdout.splitlines() if "warning" not in line.lower()
        )
        filtered_stderr = "\n".join(
            line for line in result.stderr.splitlines() if "warning" not in line.lower()
        )
        return result.returncode, filtered_stdout, filtered_stderr
    except Exception as e:
        return 1, "", str(e)

def simple_diff(old_text, new_text):
    """
    Return diff comparing two API specs 
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="Original Spec", tofile="Final Spec")
    return ''.join(diff)

def correct_spec_with_llm(api_spec_content, ruleset_content, spectral_errors):
    """
    Calls the OpenRouter API to correct the API spec
    """

    prompt = (
        "You are an expert API developer. Please perform the following steps in order:\n"
        "1. Review ONLY the error messages returned by the Spectral API Linter:\n\n"
        f"{spectral_errors}\n\n"
        "2. Briefly confirm that you have reviewed these errors by listing them in a short summary.\n\n"
        "3. Consult the following ruleset to understand what each error means:\n\n"
        f"{ruleset_content}\n\n"
        "4. Based on the above, fix the following OpenAPI specification so that it passes validation. "
        "IMPORTANT: Modify only the parts of the spec that are causing the errors.\n\n"
        f"{api_spec_content}\n\n"
        "Return ONLY the corrected API specification in valid YAML format, with no additional commentary or explanation."
    )
    
    payload = {
        "model": "qwen/qwq-32b:free",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that corrects OpenAPI specifications based on validation errors."},
            {"role": "user", "content": prompt}
        ]
    }
    
    headers = {
        "Authorization": "Bearer " + OPENROUTER_API_KEY,
        "Content-Type": "application/json"
    }
    
    #Call LLM with api_spec, ruleset and errors returned by spectral linter
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps(payload)
        )
        response.raise_for_status()
        print("Raw LLM response:")
        print(response.text)
        resp_json = response.json()
        message = resp_json["choices"][0]["message"]
        corrected_spec = message.get("content", "").strip()
        if not corrected_spec:
            print("No content returned; using reasoning field for debugging:")
            corrected_spec = message.get("reasoning", "").strip()
        return corrected_spec
    except Exception as e:
        print("Error calling OpenRouter LLM:", e)
        return api_spec_content

def main():
    spec_file = "api_spec.yaml"
    ruleset_file = "ruleset.yaml"

    # Load API spec and ruleset. Store the original spec for diff comparison
    with open(spec_file) as f:
        original_spec = f.read()
    with open(ruleset_file) as f:
        ruleset = f.read()

    print("Loaded API Spec:")
    print(original_spec)
    print("Loaded Ruleset:")
    print(ruleset)

    api_spec = original_spec

    # Limit iteretations to avoid infinite loop
    for i in range(1, 6):
        print(f"\nIteration {i}: Validating spec with Spectral...")
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".yaml", delete=False) as tmp:
            tmp.write(api_spec)
            tmp_name = tmp.name
        
        #Get output from Spectral API Linter
        code, stdout, stderr = run_spectral(tmp_name, ruleset_file)
        os.remove(tmp_name)
        print("Spectral stdout:")
        print(stdout)
        print("Spectral stderr:")
        print(stderr)
        
        # Code == 0 --> validation passed
        if code == 0:
            # If spec passes on the first try, no need for changes
            if i == 1:
                print("Validation passed, no changes done.")
            else:
                print("Spec validated successfully!")
                
            with open("corrected_api_spec.yaml", "w") as f:
                f.write(api_spec)
                
            #Write changes from original and final api spec to a changelog file
            diff = simple_diff(original_spec, api_spec)
            if diff:
                changelog_entry = f"Final diff:\n{diff}\n\n"
            else:
                changelog_entry = "Final diff: No changes were made from the original spec.\n\n"
            with open("changelog.txt", "w") as f:
                f.write(changelog_entry)
            print("Final validated spec saved to corrected_api_spec.yaml")
            print("Changelog updated in changelog.txt")
            return
        #Validation failed 
        else:
            print("Validation failed. Requesting correction from LLM...")
            # Call LLLm with api spec, ruleset and output from Spectral Linter
            new_spec = correct_spec_with_llm(api_spec, ruleset, stdout)
            print("LLM returned spec:")
            print(new_spec)
            # Update api_spec for the next iteration.
            api_spec = new_spec
    

if __name__ == "__main__":
    main()