"""
File: motor.py
Author: William Bowley
Version: 1.2
Date: 2025-07-23

Description:
    Custom linear motor for high performance 3d printers.
    - Hallow Magnets with a centeral caborn fibre support rod
    - Teflon Casing -> Two parts ()
"""



import pathlib
import yaml
import logging
import math

from bluefin.motor.interface import LinearBase

from bluefin.motor.utils import require
from bluefin.femm_utils.preprocesses.boundary import add_bounds
from bluefin.femm_utils.preprocesses.draw import draw_and_set_properties
from bluefin.domain.generation.geometry import origin_points
from bluefin.domain.generation.number_turns import estimate_turns
from bluefin.femm_utils.interface import femm_setup
from bluefin.femm_utils.preprocesses.materials import (
    add_femm_material, add_custom_material, load_materials
)

from bluefin.femm_utils.preprocesses.actions import (
    femm_set_currents, femm_step
)


class Tubular(LinearBase):
    """
    Model for bluefin tubular linear motor.

    Units and conventions:
        - All dimensions are in millimeters (mm)
        - Angular measurements are in radians expect for FEMM inputs
        - Coordinate system:
            * Uses an axial (axi) 2D FEMM Model
            * r-axis corresponds to the radial direction
            * z-axis corresponds to the linear/axial direction
        - Currents are in amperes (A)
        - Stepping is represented as linear displacement along the x-axis
    """
    def __init__(self, parameter_file) -> None:
        # FEMM groups
        self.group_boundary: int = 0
        self.group_slot: int = 1
        self.group_pole: int = 2
        self.group_tube: int = 3

        # Motor phases
        self._phases = ["phase_a", "phase_b", "phase_c"]

        # Load parameters
        self._unpack(parameter_file)

    def setup(self) -> None:
        """
        Setup femm file and draws motor geometry to simulation space
        """
        path = pathlib.Path(self.folder_path) / f"{self.file_name}.fem"
        femm_setup(
            self,
            "axi",
            path
        )

    def set_currents(self, currents: tuple[float, float, float]) -> None:
        """Set 3-phase currents for the simulation step."""
        femm_set_currents(self.phases, currents)

    def step(self, step: float) -> None:
        """Move the motor by a specified linear step."""
        femm_step(self.moving_group, step, math.pi / 2)

    def add_armature(self) -> None:
        """
        Adds the armuture to the simulation space.
        This includes the alternating polarity slot with pattern
        """

        # Calculates the slot origins (bottom-left vertex)
        slot_origins = origin_points(
            self.number_slots,
            0,
            self.slot_pitch,
            x_offset= self.slot_inner_radius,

        )

        # Calculates turns within the slot cross section
        number_turns = estimate_turns(
            self.slot_thickness,
            self.slot_axial_length,
            self.slot_wire_diameter,
            self.fill_factor
        )

        for index, origin in enumerate(slot_origins):
            # Sets phase of slot in pattern [a,b,c]
            phase = self.phases[index % len(self.phases)]

            # Alternate positive turns and negative turns for slots
            turns = number_turns if index % 2 == 0 else -number_turns

            # Draw the slot and assign its physical/material properties
            draw_and_set_properties(
                origin,
                self.slot_thickness,
                self.slot_axial_length,
                self.slot_material,
                0,  # No magnetization
                phase,
                self.group_slot,
                turns
            )

    def add_stator(self) -> None:
        """
        Adds the stator to the simulation space.
        This includes alternating magnetized poles and the structural tube.
        """

        # Generate pole origin points, shifted axially by extra pairs
        pole_origins = origin_points(
            self.total_number_poles,
            0,
            self.pole_pitch,
            y_offset=-2 * (self.extra_pairs * self.pole_pitch),
            x_offset=self.pole_inner_radius
        )

        for index, origin in enumerate(pole_origins):
            # Alternate magnetization direction every pole (e.g., N-S-N-S)
            pole_magnetization = 90 if index % 2 == 0 else -90

            # Draw the poles and assign its physical/material properties
            draw_and_set_properties(
                origin,
                self.pole_thickness,
                self.pole_axial_length,
                self.pole_material,
                pole_magnetization,
                "<none>",
                self.group_pole,
                0
            )

    def add_boundary(self) -> None:
        """
        Adds the Neumann outer boundary with
        a safety margin to enclose all geometry.
        """
        # origin boundary midway along poles
        origin = (0, self.pole_axial_length * self.number_poles * 0.5)

        # Radial extent based on stator poles and pitch
        stator_radius = 0.5 * (self.total_number_poles) * self.pole_pitch

        # Radial extent including armature and slot height
        armature_radius = self.slot_outer_radius

        # Use larger radius and add 20% margin for safety
        radius = max(stator_radius, armature_radius) * 1.2

        add_bounds(
            origin,
            radius,
            material=self.boundary_material
        )

    def compute_geometry(self) -> None:
        """
        Compute and set key geometric parameters for this motor class,
        including slot pitch, motor circumference, pole pitch
        """
        
        air_gaps = 1 * self.slot_axial_spacing

        self.slot_axial_length = (
            (self.pole_axial_length * self.number_poles + air_gaps) / self.number_slots
        ) - self.slot_axial_spacing

        self.slot_pitch = self.slot_axial_length + self.slot_axial_spacing
        self._circumference = self.slot_pitch * self.number_slots - air_gaps
        self.pole_pitch = self._circumference / self.number_poles
        self.total_number_poles = (4 * self.extra_pairs) + self.number_poles

        import logging
        logging.info(f"Calculated slot_axial_length: {self.slot_axial_length:.6f}")
        # Calculate total number of poles
        # Extra pairs add poles symmetrically on both sides
        self.total_number_poles = (4 * self.extra_pairs) + self.number_poles

    def add_materials(self) -> None:
        """
        Add motor materials to the simulation space
        """
        materials = load_materials()

        add_femm_material(materials, self.slot_material)
        add_femm_material(materials, self.pole_material)
        add_femm_material(materials, self.boundary_material)

    def get_parameters(self) -> dict:
        """
        Return a dict of all public instance variables
        """
        public_vars = {}
        for key, value in self.__dict__.items():
            if not key.startswith("_"):
                public_vars[key] = value
        public_vars["motor_class"] = self.__class__.__name__
        return public_vars

    @property
    def phases(self) -> list[str]:
        """
        Returns the phases in the motor
        """
        return self._phases

    @property
    def path(self) -> str:
        """
        Returns the full file path of the motor simulation file.
        """
        return pathlib.Path(self.folder_path) / self.file_name

    @property
    def moving_group(self) -> str:
        """
        Returns the moving group(s) within the FEMM simulation domain.
        """
        return self.group_slot

    @property
    def circumference(self) -> float:
        """
        Returns the mechanical circumference of the stator path.
        """
        return self._circumference

    @property
    def number_poles(self) -> int:
        """
        Returns the total number of magnetic poles in the motor.
        """
        return self._number_poles

    @property
    def number_slots(self) -> int:
        """
        Returns the total number of stator slots in the motor.
        """
        return self._number_slots

    @property
    def peak_currents(self) -> tuple[float, float]:
        """
        Returns the peak d-axis and q-axis currents for simulation.
        """
        return (self.d_currents, self.q_currents)

    def _unpack(self, parameter_file: str) -> None:
        """
        Loads parameters from .yaml file into variables within the class
        """
        param_file = pathlib.Path(parameter_file)

        # Existence check
        if not param_file.exists():
            msg = f"Parameter file '{param_file}' was not found."
            raise FileNotFoundError(msg)

        # Type check
        if param_file.suffix.lower() != ".yaml":
            msg = f"File '{param_file}' has wrong extension; expected '.yaml'"
            raise ValueError(msg)

        # Attempts to read the parameter file
        try:
            with open(param_file, "r", encoding="utf-8") as file:
                parameters = yaml.safe_load(file)
        except yaml.YAMLError as e:
            msg = f"Failed to parse YAML file '{param_file}' : {e}"
            raise ValueError(msg) from e

        # Check for required sections in the parameter file
        required_sections = ["model", "slot", "pole", "output"]

        for section in required_sections:
            # Existence check for required sections
            if section not in parameters:
                msg = f"Missing required key '{section}' in {param_file}"
                raise KeyError(msg)

        # Yaml Sections
        model = parameters["model"]
        slot = parameters["slot"]
        pole = parameters["pole"]
        output = parameters["output"]

        # Assign model parameters
        self._number_slots = require("number_slots", model)
        self._number_poles = require("number_poles", model)
        self.extra_pairs = require("extra_pairs", model)

        self.d_currents = require("d_currents", model)
        self.q_currents = require("q_currents", model)

        self.fill_factor = require("fill_factor", model)
        self.boundary_material = require("boundary_material", model)

        # Assign slot parameters
        self.slot_inner_radius = require("inner_radius", slot)
        self.slot_outer_radius = require("outer_radius", slot)
        self.slot_axial_length = require("axial_length", slot)
        self.slot_axial_spacing = require("axial_spacing", slot)

        self.slot_material = require("material", slot)
        self.slot_wire_diameter = require("wire_diameter", slot)

        # Assign pole parameters
        self.pole_inner_radius = require("inner_radius", pole)
        self.pole_outer_radius = require("outer_radius", pole)
        self.pole_axial_length = require("axial_length", pole)
        self.pole_material = require("material", pole)

        # Calculates radial thickness for slot, tube & poles
        self.slot_thickness = self.slot_outer_radius - self.slot_inner_radius
        self.pole_thickness = self.pole_outer_radius - self.pole_inner_radius

        # Assign output
        self.folder_path = require("folder_path", output)
        self.file_name = require("file_name", output)
