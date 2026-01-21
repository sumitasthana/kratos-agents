from multiprocessing import Pool, cpu_count
from artifact_extractor import extract_artifacts

def process_in_parallel(repo_path, extensions=None, keywords=None):
    """
    Optimize artifact extraction by processing in parallel.

    :param repo_path: Path to the Git repository.
    :param extensions: List of file extensions to include (e.g., ['.py']).
    :param keywords: List of keywords to search for in file content.
    :return: Combined results from parallel processing.
    """
    # Split the repository into chunks for parallel processing
    num_workers = cpu_count()
    chunks = [(repo_path, extensions, keywords) for _ in range(num_workers)]

    with Pool(num_workers) as pool:
        results = pool.starmap(extract_artifacts, chunks)

    # Combine results from all workers
    combined_results = []
    for result in results:
        combined_results.extend(result)

    return combined_results