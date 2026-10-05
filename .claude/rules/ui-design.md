# UI_DESIGN.md

This document defines the strict UI design system, structural conventions, and best practices Claude must follow when generating or modifying frontend code using NiceGUI.

## 1. Core Design Philosophy
- **Minimalist & Functional:** Prioritize data density and clarity. Avoid unnecessary borders, heavy drop shadows, or cluttered layouts.
- **Tailwind-First Styling:** Use Tailwind utility classes via the `.classes()` method for all styling instead of writing custom CSS.
- **Responsive by Default:** Always use flexbox/grid (`w-full`, `flex`, `grid`, `md:grid-cols-2`) to ensure pages adapt to both desktop and tablet views.
- **Modular Components:** Never write a monolithic page. Break down complex UI sections into standalone Python functions that return UI elements.

## 2. Theming & Color Palette
Maintain a consistent, professional theme across all pages. Use Tailwind color utility classes systematically:
- **Primary Action:** `bg-blue-600 text-white hover:bg-blue-700` (Main buttons, primary toggles)
- **Secondary Action:** `bg-gray-100 text-gray-800 hover:bg-gray-200` (Cancel buttons, secondary tabs)
- **Destructive Action:** `bg-red-500 text-white hover:bg-red-600` (Delete, reset operations)
- **Backgrounds:**
  - App Background: `bg-slate-50`
  - Card/Container: `bg-white shadow-sm border border-slate-200 rounded-lg`
- **Typography:**
  - Headers: `text-slate-900 font-semibold text-xl`
  - Body: `text-slate-700 text-base`
  - Muted/Labels: `text-slate-500 text-sm`

## 3. Layout Structure
Every page must follow this standard wrapper pattern to ensure navigation and spatial consistency:

```python
from nicegui import ui

def standard_layout():
    """Provides the standard shell for all pages."""
    with ui.header().classes('bg-white border-b border-slate-200 p-4 flex justify-between items-center shadow-none'):
        ui.label('Decision Intelligence').classes('text-xl font-bold text-slate-800')
        # Navigation links go here
        
    with ui.left_drawer().classes('bg-slate-50 border-r border-slate-200 p-4'):
        # Sidebar menu goes here
        pass
        
    # Main content area wrapper
    return ui.column().classes('w-full max-w-5xl mx-auto p-6 gap-6')