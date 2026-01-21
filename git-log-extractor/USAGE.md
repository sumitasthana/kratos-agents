# Usage Guide: GitHub Lineage Artifact Extractor

This guide provides step-by-step instructions to run and demo the GitHub Lineage Artifact Extractor.

---

## Prerequisites

1. **Python Installation**:
   - Ensure Python 3.8+ is installed on your system.
   - Verify installation by running:
     ```bash
     python --version
     ```

2. **Install Dependencies**:
   - Navigate to the project directory:
     ```bash
     cd c:/LangChain/Kratos-Code/spark_lineage_analyzer/git-log-extractor
     ```
   - Install required Python packages:
     ```bash
     pip install -r requirements.txt
     ```

3. **Git Repository**:
   - Ensure you have access to the Git repository you want to analyze.
   - Clone the repository locally if not already done using the following command:
     ```bash
     git clone <repository_url>
     ```

---

## Running the Extractor

1. **Navigate to the Project Directory**:
   ```bash
   cd c:/LangChain/Kratos-Code/spark_lineage_analyzer/git-log-extractor/src
   ```

2. **Run the Main Script**:
   - Use the following command to run the extractor:
     ```bash
     python main.py <path_to_git_repo> [file_extensions] [keywords]
     ```
     - `<path_to_git_repo>`: Path to the cloned repository (e.g., `C:\LangChain\Kratos-Code\spark_lineage_analyzer\git-log-extractor\gex-accel`).
     - `[file_extensions]`: (Optional) Comma-separated file extensions to filter (e.g., `.py`).
     - `[keywords]`: (Optional) Comma-separated keywords to filter files (e.g., `SparkSession`).

3. **Provide Inputs**:
   - The script will prompt you for the following inputs:
     - **Path to the Git repository**: Provide the path to the cloned repository (e.g., `C:\LangChain\Kratos-Code\spark_lineage_analyzer\git-log-extractor\gex-accel`).
     - **Optional file extensions to filter**: Specify file extensions to analyze (e.g., `.py` for Python files). Leave blank to include all files.
     - **Optional keywords to filter files**: Provide keywords to search within files (e.g., `SparkSession`). Leave blank to analyze all files.

   **Example**:
   - Path to the Git repository: `C:\LangChain\Kratos-Code\spark_lineage_analyzer\git-log-extractor\gex-accel`
   - File extensions: `.py`
   - Keywords: `SparkSession`

4. **View Output**:
   - The extracted lineage artifacts will be saved as a JSON file in the project directory.
   - Logs will be available in `extractor.log` for debugging and monitoring.

---

## Example Demo

1. **Clone a Sample Repository**:
   ```bash
   git clone https://github.com/apache/spark.git
   ```

2. **Run the Extractor**:
   ```bash
   python main.py
   ```
   - Input the path to the cloned repository (e.g., `path/to/spark`).
   - Specify `.py` as the file extension.
   - Leave keywords blank to analyze all Python files.

3. **Check Results**:
   - Open the generated JSON file to view the extracted lineage artifacts.
   - Review the `extractor.log` file for detailed logs.

---

## Notes

- Ensure the repository has a valid Git history.
- Use filters (extensions and keywords) to narrow down the analysis for large repositories.
- For performance optimization, the tool uses multiprocessing to handle large repositories efficiently.

---

For further assistance, refer to the source code or contact the project maintainer.