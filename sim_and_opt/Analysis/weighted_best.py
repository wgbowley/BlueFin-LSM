import json

# Define the file path for the simulation results.
file_path = "50x40_simulation_results.json"

# Define the weights for each characteristic.
# The order corresponds to:
# (Average Force, Force Per Watt, Average Inductance, Peak-to-Peak Force)
weights = (5, 2, -1, -1)


def calculate_score(fitness_data, weights):
    """
    Calculates a single weighted score for a motor's fitness data.

    Args:
        fitness_data (dict): A dictionary containing the motor's fitness values.
        weights (tuple): A tuple of weights for each characteristic.

    Returns:
        float: The calculated score.
    """
    try:
        # Extract fitness values based on their names in the JSON.
        average_force = fitness_data.get("Average Force", 0)
        force_per_watt = fitness_data.get("Force Per Watt", 0)
        average_inductance = fitness_data.get("Average Inductance", 0)
        peak_to_peak_force = fitness_data.get("Peak-to-Peak Force", 0)

        # Calculate the score using the provided weights.
        score = (
            weights[0] * average_force + weights[1] * force_per_watt + weights[2] * average_inductance + weights[3] * peak_to_peak_force
        )
        return score
    except TypeError as e:
        print(f"Error calculating score for fitness data: {fitness_data}. Error: {e}")
        return float('-inf')


def find_best_motor(data, weights):
    """
    Finds the motor with the highest weighted score from the simulation data.

    Args:
        data (dict): The loaded JSON data.
        weights (tuple): A tuple of weights for each characteristic.

    Returns:
        tuple: A tuple containing the best motor's data and its score, or (None, None) if no completed motors are found.
    """
    best_motor = None
    best_score = float('-inf')  # Initialize with a very low number

    # The data is structured by 'generations'. We need to check all individuals.
    for generation in data:
        for motor in generation.get("individuals", []):
            # We only want to evaluate motors that have a "completed" status.
            if motor.get("status") == "completed":
                # Calculate the score for the current motor.
                fitness_data = motor.get("fitness", {})
                current_score = calculate_score(fitness_data, weights)

                # Check if this motor has a better score than the current best.
                if current_score > best_score:
                    best_score = current_score
                    best_motor = motor

    return best_motor, best_score


# --- Main script execution ---
if __name__ == "__main__":
    try:
        # Load the JSON data from the file.
        with open(file_path, 'r') as f:
            simulation_data = json.load(f)

        # Find the best motor using our functions.
        best_motor, best_score = find_best_motor(simulation_data, weights)

        if best_motor:
            # Print the results in a clear format.
            print("--- Best Linear Motor Found ---")
            print(f"Score: {best_score:.2f}")
            print("\nMotor Characteristics:")
            print(f"  Slot thickness: {best_motor.get('Slot thickness', 'N/A')}")
            print(f"  Slot axial length: {best_motor.get('Slot axial length', 'N/A')}")
            print(f"  Slot axial spacing: {best_motor.get('Slot axial spacing', 'N/A')}")
            print(f"  Wire diameter: {best_motor.get('Wire diameter', 'N/A')}")
            print("\nFitness Metrics:")
            fitness = best_motor.get("fitness", {})
            for key, value in fitness.items():
                print(f"  {key}: {value}")
        else:
            print("No completed motors found in the simulation results.")

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode the JSON file '{file_path}'. Please check its format.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
