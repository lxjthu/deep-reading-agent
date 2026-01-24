import os
import argparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def inject_links(folder_path: str):
    """
    Scans a folder for L1-L4 and Full Report MD files and injects bidirectional links.
    """
    files = os.listdir(folder_path)
    md_files = [f for f in files if f.endswith(".md")]
    
    # Identify files
    full_report = None
    layers = {}
    
    for f in md_files:
        if "_Full_Report.md" in f:
            full_report = f
        elif "_L1_" in f:
            layers["L1"] = f
        elif "_L2_" in f:
            layers["L2"] = f
        elif "_L3_" in f:
            layers["L3"] = f
        elif "_L4_" in f:
            layers["L4"] = f
            
    if not full_report:
        logger.warning(f"No Full Report found in {folder_path}, skipping.")
        return

    # Links Map
    # Key: Current File, Value: List of links to append
    links_map = {}
    
    # 1. Full Report links to all Layers
    links_to_layers = []
    for k, v in sorted(layers.items()):
        links_to_layers.append(f"- [[{v}|{k} Layer]]")
    
    links_map[full_report] = ["\n## Related Files"] + links_to_layers

    # 2. Layers link to Full Report and other Layers
    for current_layer_key, current_file in layers.items():
        links = ["\n## Navigation"]
        links.append(f"- [[{full_report}|Back to Full Report]]")
        
        # Add links to next/prev layers
        layer_keys = sorted(layers.keys())
        curr_idx = layer_keys.index(current_layer_key)
        
        if curr_idx > 0:
            prev_key = layer_keys[curr_idx - 1]
            links.append(f"- Previous: [[{layers[prev_key]}|{prev_key}]]")
        
        if curr_idx < len(layer_keys) - 1:
            next_key = layer_keys[curr_idx + 1]
            links.append(f"- Next: [[{layers[next_key]}|{next_key}]]")
            
        links_map[current_file] = links

    # Apply changes
    for filename, lines_to_add in links_map.items():
        file_path = os.path.join(folder_path, filename)
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Check if links already exist to avoid duplication
        if "## Navigation" in content or "## Related Files" in content:
            logger.info(f"Skipping {filename}, links already present.")
            continue
            
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines_to_add))
            f.write("\n")
            
        logger.info(f"Injected links into {filename}")

def main():
    parser = argparse.ArgumentParser(description="Inject bidirectional links into Social Science Reports")
    parser.add_argument("results_dir", help="Root directory containing paper subfolders")
    args = parser.parse_args()

    if not os.path.exists(args.results_dir):
        logger.error(f"Directory not found: {args.results_dir}")
        return

    # Iterate over subdirectories (each paper has its own folder)
    for item in os.listdir(args.results_dir):
        item_path = os.path.join(args.results_dir, item)
        if os.path.isdir(item_path):
            logger.info(f"Processing folder: {item}")
            inject_links(item_path)

if __name__ == "__main__":
    main()
