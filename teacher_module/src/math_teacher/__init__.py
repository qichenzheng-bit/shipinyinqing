"""Independent math teacher module; no video/frontend/backend integration."""
from .models import TeacherInput, TeachingPackage
from .pipeline import MathTeacherPipeline

__all__ = ["TeacherInput", "TeachingPackage", "MathTeacherPipeline"]
