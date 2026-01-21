# UI/UX Enhancement Plan for Gym Tracker

## 1. Adopt KivyMD (Material Design)
The current app uses standard Kivy widgets which are functional but have a "desktop/legacy" look. Moving to **KivyMD** will instantly modernize the app with:
- **Material Design Components**: Buttons, TextFields, Cards, and Navigation Bars that look like a native Android/iOS app.
- **Theming**: easy switching between Light/Dark modes and changing primary color palettes.
- **Iconography**: Built-in access to material icons.

**Action Item:** Install KivyMD (`pip install kivymd`) and refactor `main.py` to use `MDApp`.

## 2. Redesign the "Workout Session" Workflow
Currently, you have to select an Exercise and Routine for *every single entry*. This is tedious during a workout.

**Proposed Workflow:**
1.  **Home Screen**: Shows a list of your Routines (e.g., "Push Day", "Leg Day").
2.  **Start Workout**: You tap "Push Day".
3.  **Active Session Screen**:
    - The app loads **ALL** exercises associated with "Push Day".
    - Displays them as a vertical list of **Cards**.
    - Each Card contains:
        - Exercise Name
        - Previous stats (Last time you did this: 3x10 @ 135lbs)
        - Inputs for today's Weight, Reps, Sets.
    - You fill them out as you go.
    - A "Finish Workout" button at the bottom saves everything at once (or save each card individually as you go).

## 3. Improve Routine Management
The "Association" screen (one spinner for Routine, one for Exercise) is slow for building complex routines.

**Proposed Interface:**
- **Routine Editor**: When editing a routine, show a list of *all* available exercises with **Checkboxes**.
- Simply check the boxes for the exercises you want in that routine and click Save.

## 4. Visual & Feedback Improvements
- **Charts**: Use a simple graph (via `kivy-garden.matplotlib` or manual drawing on Canvas) to visualize the "Change Over Time" rather than just text labels.
- **Toasts/Snackbars**: Instead of a generic "Status Label" at the bottom, use floating Snackbars for success messages ("Saved Bench Press!").

## Mockup of the "Active Session" Card (KivyMD style)
```python
MDCard:
    orientation: "vertical"
    size_hint_y: None
    height: "150dp"
    padding: "10dp"
    
    MDLabel:
        text: "Bench Press"
        theme_text_color: "Primary"
        font_style: "H6"
        
    MDLabel:
        text: "Last: 135lbs x 10"
        theme_text_color: "Secondary"
        font_style: "Caption"
        
    BoxLayout:
        spacing: "10dp"
        MDTextField:
            hint_text: "Weight"
            mode: "rectangle"
        MDTextField:
            hint_text: "Reps"
            mode: "rectangle"
        MDTextField:
            hint_text: "Sets"
            mode: "rectangle"
            
    MDRaisedButton:
        text: "Log Set"
        pos_hint: {"right": 1}
```
