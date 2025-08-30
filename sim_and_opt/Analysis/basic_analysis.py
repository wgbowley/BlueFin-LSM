"""
Filename: basic_analysis.py
Author: William Bowley
Version: 1.1
Date: 2025-07-14

Description:
    Runs a rotational analysis on a tubular motor using a configuration file.
    Outputs selected results to JSON and plots Lorentz forces versus
    displacement.
"""

import matplotlib.pyplot as plt
import os
import sys

# Applies project root directory dynamically
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Framework imports
from bluefin.simulations.alignment import phase_alignment
from bluefin.simulations.rotational_analysis import rotational_analysis
from bluefin.output.selector import OutputSelector
from bluefin.output.writer import write_output_json
from models.iron_tubular.motor import Tubular

# --- Configuration ---
numSamples = 100
motorConfigPath = "models/iron_tubular/single.yaml"
outputPath = "test.json"
requestedOutputs = ["force_lorentz"]

# --- Initialize and simulate ---
motor = Tubular(motorConfigPath)
print(motor.setup())

# Only required for some models
# Makes sure flux of the stator & armature are aligned
phase_offset = phase_alignment(motor, 20)

outputSelector = OutputSelector(requestedOutputs)
subjects = {"group": motor.moving_group, "phaseName": motor.phases}

results = rotational_analysis(motor, outputSelector, subjects, numSamples, phase_offset)

# Save results to JSON file
write_output_json(results, "sim_and_opt/rotational_analysis_results.json")

# --- Plotting ---
positions = [result["displacement"] for result in results]
lorentzForces = [result["outputs"]["force_lorentz"][0] for result in results]

plt.figure(figsize=(8, 5))
plt.ylim(0, 1.1 * max(lorentzForces))
plt.plot(positions, lorentzForces, label="Lorentz Force", color='blue')
plt.xlabel("Displacement (mm)")
plt.ylabel("Force via Lorentz (N)")
plt.title("Tubular Motor Force vs Displacement 20 by 11 in 5 and N52")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
