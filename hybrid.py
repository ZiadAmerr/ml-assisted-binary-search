import os
import numpy as np
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from tqdm import tqdm
import pandas as pd



def add_uniform_noise(probas, noise_level=0.1):
    """
    Adds random uniform noise to a list of probabilities.

    Parameters:
    probas (list of float): List of probabilities to add noise to.
    noise_level (float): Maximum amount of noise to add. Noise will be in the range [-noise_level, noise_level].

    Returns:
    list of float: Probabilities with added noise.
    """
    noise = np.random.uniform(-noise_level, noise_level, len(probas))
    probas += noise
    probas = (probas - min(probas)) / (max(probas) - min(probas))

    return probas

def get_value(y, index):
    x = y[index]
    return x

# loss calculation 
def wBCE_loss(y, y_hat):
    # Calculate the lambda value
    N_bad = np.sum(y)
    N = len(y)
    N_good = N - N_bad
    lam = N_good / N

    # Ensure y_hat values are in (0, 1)
    epsilon = 1e-8
    y_hat = np.clip(y_hat, epsilon, 1 - epsilon)

    # Calculate the weighted BCE loss
    wBCE_loss = (-2 / N) * np.sum(
        lam * y * np.log(y_hat) + (1 - lam) * (1 - y) * np.log(1 - y_hat)
    )

    return wBCE_loss



def diffs2(probas):
    probas = np.array(probas)
    left_sums = np.cumsum(probas)[:-1]
    total_sum = np.sum(probas)
    right_sums = total_sum - left_sums
    differences = np.abs(left_sums - right_sums)
    return differences.tolist()


# Binary search algorithm
def binary_search(commits):
    num_of_runs = 0
    len_commits = len(commits)
    low, high = 0, len_commits - 1

    state_of_first = get_value(commits, 0)
    state_of_last = get_value(commits, len_commits - 1)

    if state_of_first == 0 and state_of_last == 0:
        return -1, num_of_runs
    
    if CONFIG["print_detailed_search"]:
        print(f"low: {low}, high: {high}")
    prev_mid = -1
    while low < high:
        mid = (low + high) // 2

        num_of_runs += 1
        if commits[mid] == 1:
            high = mid

        elif commits[mid] == 0:
            low = mid + 1
        
        if CONFIG["print_detailed_search"]:
            print(f"runs: {num_of_runs}, low: {low}, mid: {prev_mid}, high: {high}")
        prev_mid = mid

    return num_of_runs, high



# Hybrid search algorithm
def hybrid_search(commits, probabilities, alpha):
    num_of_runs = 0
    len_commits = len(commits)
    low, high = 0, len_commits - 1

    state_of_first = get_value(commits, 0)
    state_of_last = get_value(commits, len_commits - 1)

    if state_of_first == 0 and state_of_last == 0:
        return -1, num_of_runs


    if alpha == 0:
        return binary_search(commits)
    
    while low < high:
        binary_mid = (low + high) // 2

        diffs_arr = diffs2(probabilities[low : high + 1])

        prob_mid = np.argmin(diffs_arr) + low

        new_mid = round(((alpha * prob_mid) + ((1 - alpha) * binary_mid)))

        num_of_runs += 1
        if commits[new_mid] == 1:
            high = new_mid

        elif commits[new_mid] == 0:
            low = new_mid + 1
        
        if CONFIG["print_detailed_search"]:
            print(f"runs: {num_of_runs}, low: {low}, high: {high}")

    return num_of_runs, high


# data generation
def get_preds_per_depth(samples, features, n_informative, min_max_depth, max_max_depth):
    samples = CONFIG["samples"]
    features = CONFIG["features"]
    min_max_depth = CONFIG["min_max_depth"]
    max_max_depth = CONFIG["max_max_depth"]
    n_informative = CONFIG["n_informative"]

    name = f"data__samples_{samples}__features_{features}__n_informative_{n_informative}__min_max_depth_{min_max_depth}__max_max_depth_{max_max_depth}.pkl"

    # check if the data is already generated
    try:
        data = pd.read_pickle(os.path.join("data", name))
        print("you saved the time of data regeneration")
        return data
    except:
        pass

    X, y = make_classification(
        n_samples=samples,
        n_features=features,
        n_redundant=10,
        n_informative=n_informative,
        n_clusters_per_class=1,
        n_classes=2,
        weights=[0.997, 0.003],
        flip_y=0.01,            # rolling back to default
        random_state=42,
    )

    data = {}
    for max_depth in tqdm(
        range(CONFIG["min_max_depth"], CONFIG["max_max_depth"] + 1), desc="Max Depth Progress", colour="green"
    ):
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=max_depth,
            min_samples_split=2,
            min_samples_leaf=1,
            random_state=42,
            n_jobs=-1,
        )

        model.fit(X, y)

        probas = model.predict_proba(X)[:, 1]
        data[max_depth] = {"preds": probas, "commits": y}
    
    pd.DataFrame(data).to_pickle(os.path.join("data", name))

    return data


def transform_data(y, predictions):
    min_chunk_size = 2 ** (CONFIG["min_log_size"] - 1) + 1
    max_chunk_size = 2 ** CONFIG["max_log_size"]
    print(f"min_chunk_size: {min_chunk_size}, max_chunk_size: {max_chunk_size}")

    index = 0
    chunks = []
    while True:
        size = np.random.randint(min_chunk_size, max_chunk_size)

        if index + size >= len(y):
            break

        y_chunk = y[index : index + size]
        preds_chunk = predictions[index : index + size]

        if sum(y_chunk) == 0 or y_chunk[0] == 1 :
            # Do not append!
            index += size
        elif sum(y_chunk) == 1:
            # Safely append
            index += size
            chunks.append({"y_chunk": y_chunk, "preds_chunk": preds_chunk})
        else:
            one_indices = [i for i, x in enumerate(y_chunk) if x == 1]

            # Make n_bad deep copies of the chunk
            y_copied_chunks = []
            pred_copied_chunks = []
            for one_index in one_indices:
                curr_chunk = y_chunk.copy()
                # set the current one_index to 1, and the rest to 0
                curr_chunk[:one_index] = 0
                curr_chunk[one_index + 1 :] = 0
                y_copied_chunks.append(curr_chunk)
                pred_copied_chunks.append(preds_chunk)

            # Append the copied chunks
            for y_copied_chunk, pred_copied_chunk in zip(
                y_copied_chunks, pred_copied_chunks
            ):
                chunks.append(
                    {"y_chunk": y_copied_chunk, "preds_chunk": pred_copied_chunk}
                )

            index += size

    for chunk in chunks:
        y_chunk = chunk["y_chunk"]
        preds_chunk = chunk["preds_chunk"]
        # Find the index of the single 1 in the chunk
        y_transformed = y_chunk.copy()
        y_transformed[np.argmax(y_chunk) + 1 :] = 1
        chunk["y_transformed"] = y_transformed
        assert len(y_chunk) == len(preds_chunk)
        assert sum(y_chunk) == 1

    return chunks


def main():
    samples, features, n_informative, min_max_depth, max_max_depth = (
        CONFIG["samples"],
        CONFIG["features"],
        CONFIG["n_informative"],
        CONFIG["min_max_depth"],
        CONFIG["max_max_depth"],
    )

    data = get_preds_per_depth(
        samples, features, n_informative, min_max_depth, max_max_depth)
    
    for _, data_entries in data.items():
        preds = data_entries["preds"]
        commits = data_entries["commits"]
        chunks = transform_data(commits, preds)

    results = []
    for alpha in np.arange(0, 1.05, 0.05): # avoid floating point errors
        for max_depth, preds_and_commits in data.items():
            preds = preds_and_commits["preds"]
            commits = preds_and_commits["commits"]
            chunks = transform_data(commits, preds)

            scores_mean = []
            saved_runs_mean = []
      

            for chunk in chunks:
                y_transformed = chunk["y_transformed"]
                # binary runs can be calculated only using the length of the array

                binary_runs, binary_index = binary_search(y_transformed)
                # binary_runs = np.ceil(np.log(len(y_transformed)))
                print("---"*20)
                print(f"alpha = {alpha}")
                print("---"*20)
                # no need to add noise to the predictions
                hybrid_runs, hybrid_index = hybrid_search(y_transformed, chunk["preds_chunk"], alpha)
                
                # check index similarity 
                assert binary_index == hybrid_index
                
                score = wBCE_loss(chunk["y_chunk"], chunk["preds_chunk"])

                saved_runs_mean.append((binary_runs - hybrid_runs) / (binary_runs - 2))
                scores_mean.append(score)


                if CONFIG["print_detailed_search"]:
                    print(f"Size: {np.ceil(np.log(len(y_transformed)))}")
                    print(f"saved runs: {(binary_runs - hybrid_runs)/(binary_runs - 2)}")
                    print("*" * 100 + "\n\n")
            
            results.append({"alpha": alpha,
                            "saved_runs": np.mean(saved_runs_mean), 
                            "loss": np.mean(scores_mean),})
        print('-'*60)
        print(f"Max Depth: {max_depth}")
        print('-'*60)

    pd.DataFrame(results).to_pickle("hybrid_vfinal.pkl")


CONFIG = {
    "samples": 100000,
    "features": 100,
    "n_informative": 40,     # changed from 90 to 40 as it gives the most stable results 
    "min_max_depth": 1,
    "max_max_depth": 40,
    "min_log_size": 8,
    "max_log_size": 10,
    "print_detailed_search": True,
}


main()


