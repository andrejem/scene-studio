"""Test setup: make the integration of this repo importable as custom_components.scene_studio."""

import os

import custom_components

custom_components.__path__.append(os.path.join(os.path.dirname(__file__), "..", "custom_components"))
