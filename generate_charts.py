import json
import os
import shutil
import matplotlib.pyplot as plt
import numpy as np

# Load data from a JSON file
home_dir = os.path.expanduser("~")
data_file = os.path.join('.', 'python-cbor-perf-data-cleaned.json')
with open(data_file, 'r') as file:
    data = json.load(file)

# Define the directory to save plots
plot_dir = os.path.join(home_dir, "plots")

# Delete all files in the plot directory
if os.path.exists(plot_dir):
    shutil.rmtree(plot_dir)
os.makedirs(plot_dir)

# Function to generate comparative bar charts for p90 values across different protocols for each dimension and operation
def generate_service_metric_bar_chart(data, service, metric):
    filtered_data = [d for d in data if d["service"] == service and d["metric"] == metric]
    if not filtered_data:
        print(f"No data found for {service} - {metric}")
        return

    dimension_test_case_pairs = list(set((d["dimension_value"], d["test-case"]) for d in filtered_data))
    protocols = list(set(d["protocol"] for d in filtered_data))
    values = {protocol: [next((d["p90"] for d in filtered_data if d["dimension_value"] == pair[0] and d["test-case"] == pair[1] and d["protocol"] == protocol), 0) for pair in dimension_test_case_pairs] for protocol in protocols}

    x = np.arange(len(dimension_test_case_pairs))  # the label locations
    width = 0.2  # the width of the bars

    fig, ax = plt.subplots(figsize=(12, 8))
    for i, protocol in enumerate(protocols):
        ax.bar(x + i * width, values[protocol], width, label=protocol)

    ax.set_xlabel('Dimension Value and Test Case')
    ax.set_ylabel('p90 Value')
    ax.set_title(f"{service} - {metric} - p90 Comparison")
    ax.set_xticks(x + width / len(protocols))
    ax.set_xticklabels([f"{pair[0]}-{pair[1]}" for pair in dimension_test_case_pairs], rotation=45, ha="right")
    ax.legend()

    plt.tight_layout()
    plt.savefig(os.path.join(plot_dir, f"{metric}_{service}_p90_comparison.png"))
    plt.close()

# Generate comparative p90 bar charts for unique combinations of service and metric
unique_combinations = {(d["service"], d["metric"]) for d in data}

for combination in unique_combinations:
    generate_service_metric_bar_chart(data, *combination)

print(f"Comparative p90 plots have been saved to {plot_dir}")
