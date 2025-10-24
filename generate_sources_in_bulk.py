import os
import glob
import subprocess

def generate_sources_in_bulk(orig_dir):
    """Generate MioGatto source files for all HTML files in the given directory"""
    
    html_files = glob.glob(os.path.join(orig_dir, "*.html"))
    successful = 0

    for html_file in html_files:
        command = ['python', '-m', 'tools.preprocess', html_file]
        
        try:
            result = subprocess.run(command, check=True)
            print(f"[SUCCESS] Preprocessed: {html_file}")

            # Optionally print the output from the subprocess
            if result.stdout:
                print("  --- Subprocess Output ---")
                print(result.stdout.strip())
                print("  -------------------------")
                
            successful+=1
        except subprocess.CalledProcessError as e:
            # Handle non-zero exit code from the preprocessing tool
            print(f"[ERROR] Failed to preprocess {html_file}. Return Code: {e.returncode}")
            print(f"  Stdout:\n{e.stdout}")
            print(f"  Stderr:\n{e.stderr}")
        except FileNotFoundError:
            # Handle if the 'python' executable or 'tools.preprocess' module is not found
            print("[FATAL ERROR] Python executable or the 'tools.preprocess' module was not found.")
            print("Ensure 'python' is in your PATH and the 'tools.preprocess' module is correctly installed/accessible.")
            break # Stop processing if a fatal error occurs
    

    print(f"\nConversion complete: {successful}/{len(html_files)} files successful")

generate_sources_in_bulk("./raw_sources/")