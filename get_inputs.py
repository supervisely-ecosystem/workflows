import json
import os
from pathlib import Path


def find_train_folder():
    """Find train folder in repository structure."""
    current_dir = Path.cwd()
    
    # Check for supervisely_integration/train
    supervisely_integration_path = current_dir / "supervisely_integration" / "train"
    if supervisely_integration_path.exists() and supervisely_integration_path.is_dir():
        return supervisely_integration_path
    
    # Check for train directly
    train_path = current_dir / "train"
    if train_path.exists() and train_path.is_dir():
        return train_path
    
    raise FileNotFoundError("Could not find train folder in repository structure")


def parse_config(config_path):
    """Parse config.json and extract framework name and models path."""
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    framework_name = config.get("framework", {}).get("name")
    models_path = config.get("files", {}).get("models")
    
    if not framework_name:
        raise ValueError("Framework name not found in config.json")
    if not models_path:
        raise ValueError("Models path not found in config.json")
    
    return framework_name, models_path


def main():
    try:
        # Check if environment variables are already set
        framework_name = os.environ.get("FRAMEWORK")
        models_path = os.environ.get("MODELS_PATH")
        
        if framework_name and models_path:
            print(f"Using existing environment variables:")
            print(f"FRAMEWORK={framework_name}")
            print(f"MODELS_PATH={models_path}")
            return
        
        # Find train folder
        train_folder = find_train_folder()
        print(f"Found train folder: {train_folder}")
        
        # Find config.json
        config_path = train_folder / "config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"config.json not found in {train_folder}")
        
        # Parse config
        framework_name, models_path = parse_config(config_path)
        
        # Set GitHub environment variables
        github_env = os.environ.get("GITHUB_ENV")
        if github_env:
            with open(github_env, "a") as f:
                f.write(f"FRAMEWORK={framework_name}\n")
                f.write(f"MODELS_PATH={models_path}\n")
            print(f"Set FRAMEWORK={framework_name}")
            print(f"Set MODELS_PATH={models_path}")
        else:
            # For local testing
            print(f"FRAMEWORK={framework_name}")
            print(f"MODELS_PATH={models_path}")
    
    except Exception as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
