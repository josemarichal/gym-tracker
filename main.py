import os
import sys
import sqlite3
import logging
from datetime import datetime, timedelta

from kivy.lang import Builder
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import platform
from kivy.properties import ObjectProperty, StringProperty, ListProperty, NumericProperty
from kivy.graphics import Color, Line, Ellipse
from kivy.uix.widget import Widget

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDIconButton, MDFloatingActionButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.dialog import MDDialog
from kivymd.uix.textfield import MDTextField
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.list import OneLineListItem

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO)

if platform == 'android':
    from android.permissions import request_permissions, Permission
    from android.storage import primary_external_storage_path, app_storage_path
    def check_permissions():
        request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
    
    try:
        base_path = app_storage_path()
    except:
        base_path = primary_external_storage_path()
else:
    def check_permissions(): pass
    base_path = os.path.dirname(os.path.abspath(__file__))

DB_FILE = os.path.join(base_path, "weight_training.db")

# --- Database Manager (Reused Logic) ---
class DatabaseManager:
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def init_db():
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS routines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS exercise_routine (
            exercise_id INTEGER,
            routine_id INTEGER,
            FOREIGN KEY(exercise_id) REFERENCES exercises(id) ON DELETE CASCADE,
            FOREIGN KEY(routine_id) REFERENCES routines(id) ON DELETE CASCADE,
            PRIMARY KEY(exercise_id, routine_id)
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS workout_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exercise_id INTEGER NOT NULL,
            routine_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            weight REAL NOT NULL,
            reps INTEGER NOT NULL,
            sets INTEGER NOT NULL,
            FOREIGN KEY(exercise_id) REFERENCES exercises(id) ON DELETE CASCADE,
            FOREIGN KEY(routine_id) REFERENCES routines(id) ON DELETE CASCADE
        )''')
        
        # Ensure schema updates
        try:
            cursor.execute("PRAGMA table_info(workout_log)")
            columns = [col['name'] for col in cursor.fetchall()]
            if "routine_id" not in columns:
                cursor.execute("ALTER TABLE workout_log ADD COLUMN routine_id INTEGER REFERENCES routines(id)")
            if "sets" not in columns:
                cursor.execute("ALTER TABLE workout_log ADD COLUMN sets INTEGER DEFAULT 1 NOT NULL")
        except Exception as e:
            logging.error(f"Schema update error: {e}")

        conn.commit()
        conn.close()

# --- Custom Widgets ---

class SimpleGraphWidget(Widget):
    '''A simple line graph widget drawn on canvas.'''
    points_data = ListProperty([]) # List of tuples (value, date_label)
    line_color = ListProperty([0, 1, 1, 1]) # Cyan default

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.redraw, size=self.redraw, points_data=self.redraw)

    def redraw(self, *args):
        self.canvas.clear()
        if not self.points_data or len(self.points_data) < 2:
            return

        # Extract values for scaling
        values = [p[0] for p in self.points_data]
        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val if max_val != min_val else 1

        with self.canvas:
            Color(*self.line_color)
            
            # Draw Line
            calc_points = []
            x_step = self.width / (len(self.points_data) - 1)
            
            for i, (val, _) in enumerate(self.points_data):
                x = self.x + (i * x_step)
                # Normalize height to 10-90% of widget height
                normalized_y = (val - min_val) / val_range
                y = self.y + (0.1 * self.height) + (normalized_y * 0.8 * self.height)
                calc_points.extend([x, y])
                
                # Draw dot at point
                Ellipse(pos=(x - 3, y - 3), size=(6, 6))

            Line(points=calc_points, width=2)


class RoutineCard(MDCard):
    '''Card representing a routine on the home screen.'''
    routine_name = StringProperty()
    routine_id = NumericProperty()
    
    def on_release(self):
        app = MDApp.get_running_app()
        app.start_session(self.routine_id, self.routine_name)

class ExerciseCard(MDCard):
    '''Card for a single exercise in an active session.'''
    exercise_name = StringProperty()
    exercise_id = NumericProperty()
    last_log = StringProperty("No previous data")
    
    # Input bindings
    weight_text = StringProperty("")
    reps_text = StringProperty("")
    sets_text = StringProperty("")

    def save_set(self):
        app = MDApp.get_running_app()
        if not self.weight_text or not self.reps_text or not self.sets_text:
            Snackbar(text="Please fill all fields").open()
            return

        try:
            weight = float(self.weight_text)
            reps = int(self.reps_text)
            sets = int(self.sets_text)
            
            app.log_set(self.exercise_id, weight, reps, sets)
            Snackbar(text=f"Saved {self.exercise_name}!").open()
        except ValueError:
            Snackbar(text="Invalid number format").open()
            
    def show_trends(self):
        app = MDApp.get_running_app()
        app.show_trend_dialog(self.exercise_id, self.exercise_name)


# --- Screens ---

class HomeScreen(MDScreen):
    def on_enter(self):
        self.load_routines()

    def load_routines(self):
        self.ids.routine_list.clear_widgets()
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM routines ORDER BY name")
        routines = cursor.fetchall()
        conn.close()

        for r in routines:
            card = RoutineCard(
                routine_name=r['name'],
                routine_id=r['id']
            )
            self.ids.routine_list.add_widget(card)

class ActiveSessionScreen(MDScreen):
    routine_name = StringProperty("")
    
    def load_exercises(self, routine_id, routine_name):
        self.routine_name = routine_name
        self.ids.exercise_list.clear_widgets()
        
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        # Get exercises for this routine
        query = """
            SELECT e.id, e.name 
            FROM exercises e
            JOIN exercise_routine er ON e.id = er.exercise_id
            WHERE er.routine_id = ?
            ORDER BY e.name
        """
        exercises = cursor.execute(query, (routine_id,)).fetchall()
        
        for ex in exercises:
            # Get last log for this exercise
            last_log = cursor.execute("""
                SELECT weight, reps, sets, date FROM workout_log 
                WHERE exercise_id = ? 
                ORDER BY date DESC LIMIT 1
            """, (ex['id'],)).fetchone()
            
            history_text = "New Exercise"
            if last_log:
                history_text = f"Last: {last_log['sets']}x{last_log['reps']} @ {last_log['weight']}lbs"

            card = ExerciseCard(
                exercise_name=ex['name'],
                exercise_id=ex['id'],
                last_log=history_text
            )
            self.ids.exercise_list.add_widget(card)
            
        conn.close()

# --- Main App ---

KV = '''
#:import hex kivy.utils.get_color_from_hex

<RoutineCard>:
    orientation: "vertical"
    padding: "16dp"
    size_hint_y: None
    height: "100dp"
    elevation: 2
    radius: [15]
    ripple_behavior: True
    md_bg_color: app.theme_cls.bg_darkest
    
    MDLabel:
        text: root.routine_name
        font_style: "H5"
        bold: True
        theme_text_color: "Custom"
        text_color: app.theme_cls.primary_color
        halign: "center"
        pos_hint: {"center_y": .5}

<ExerciseCard>:
    orientation: "vertical"
    padding: "16dp"
    size_hint_y: None
    height: "220dp"
    elevation: 1
    radius: [10]
    md_bg_color: app.theme_cls.bg_dark
    spacing: "10dp"

    BoxLayout:
        size_hint_y: None
        height: "30dp"
        
        MDLabel:
            text: root.exercise_name
            font_style: "H6"
            theme_text_color: "Primary"
            size_hint_x: 0.8
            halign: 'left'
            valign: 'center'
        
        MDIconButton:
            icon: "chart-line"
            theme_text_color: "Custom"
            text_color: app.theme_cls.accent_color
            pos_hint: {"center_y": .5}
            on_release: root.show_trends()
    
    MDLabel:
        text: root.last_log
        font_style: "Caption"
        theme_text_color: "Secondary"

    GridLayout:
        cols: 3
        spacing: "10dp"
        size_hint_y: None
        height: "60dp"

        MDTextField:
            hint_text: "Lbs"
            text: root.weight_text
            on_text: root.weight_text = self.text
            input_filter: "float"
            mode: "rectangle"

        MDTextField:
            hint_text: "Reps"
            text: root.reps_text
            on_text: root.reps_text = self.text
            input_filter: "int"
            mode: "rectangle"

        MDTextField:
            hint_text: "Sets"
            text: root.sets_text
            on_text: root.sets_text = self.text
            input_filter: "int"
            mode: "rectangle"

    MDRaisedButton:
        text: "LOG THIS"
        size_hint_x: 1
        on_release: root.save_set()

ScreenManager:
    id: screen_manager
    HomeScreen:
        name: "home"
    ActiveSessionScreen:
        name: "session"

<HomeScreen>:
    MDBoxLayout:
        orientation: "vertical"
        
        MDTopAppBar:
            title: "Gym Tracker Pro"
            elevation: 4
            
        ScrollView:
            MDBoxLayout:
                id: routine_list
                orientation: "vertical"
                padding: "20dp"
                spacing: "15dp"
                adaptive_height: True

    MDFloatingActionButton:
        icon: "plus"
        pos_hint: {"right": .95, "bottom": .05}
        on_release: app.show_add_options()

<ActiveSessionScreen>:
    MDBoxLayout:
        orientation: "vertical"
        
        MDTopAppBar:
            title: root.routine_name
            left_action_items: [["arrow-left", lambda x: app.go_home()]]
            elevation: 4

        ScrollView:
            MDBoxLayout:
                id: exercise_list
                orientation: "vertical"
                padding: "15dp"
                spacing: "15dp"
                adaptive_height: True
'''

class GymTrackerApp(MDApp):
    current_routine_id = NumericProperty(0)
    dialog = None

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.accent_palette = "Teal"
        self.theme_cls.bg_darkest = [0.15, 0.15, 0.15, 1]
        
        check_permissions()
        DatabaseManager.init_db()
        return Builder.load_string(KV)

    def go_home(self):
        self.root.current = "home"

    def start_session(self, routine_id, routine_name):
        self.current_routine_id = routine_id
        session_screen = self.root.get_screen("session")
        session_screen.load_exercises(routine_id, routine_name)
        self.root.transition.direction = 'left'
        self.root.current = "session"

    def log_set(self, exercise_id, weight, reps, sets):
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cursor.execute("""
                INSERT INTO workout_log (exercise_id, routine_id, date, weight, reps, sets)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (exercise_id, self.current_routine_id, date_str, weight, reps, sets))
            conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error logging set: {e}")
            Snackbar(text="Database Error!").open()
        finally:
            conn.close()

    def show_trend_dialog(self, exercise_id, exercise_name):
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        # Get history sorted by date
        data = cursor.execute("""
            SELECT weight, date FROM workout_log 
            WHERE exercise_id = ? 
            ORDER BY date ASC
        """, (exercise_id,)).fetchall()
        conn.close()

        if not data:
            Snackbar(text=f"No data yet for {exercise_name}").open()
            return

        # Process data for graph
        # We'll take the max weight per day if there are duplicates, to keep the graph simple
        points = []
        for row in data:
            try:
                dt = datetime.strptime(row['date'], "%Y-%m-%d %H:%M:%S")
            except:
                try: 
                     dt = datetime.strptime(row['date'], "%Y-%m-%d")
                except: continue
            
            points.append((row['weight'], dt.strftime("%m/%d")))

        # Create Content
        content = MDBoxLayout(orientation="vertical", size_hint_y=None, height="200dp")
        
        # Add summary stats
        max_weight = max([p[0] for p in points]) if points else 0
        content.add_widget(MDLabel(
            text=f"Personal Record: {max_weight} lbs\nLog Entries: {len(points)}",
            theme_text_color="Secondary",
            size_hint_y=None, height="40dp"
        ))

        # Add Graph
        graph = SimpleGraphWidget(size_hint_y=None, height="150dp")
        graph.points_data = points
        graph.line_color = self.theme_cls.accent_color
        content.add_widget(graph)

        self.dialog = MDDialog(
            title=f"{exercise_name} Progress",
            type="custom",
            content_cls=content,
            buttons=[
                MDRaisedButton(
                    text="CLOSE",
                    on_release=lambda x: self.dialog.dismiss()
                )
            ],
        )
        self.dialog.open()

    def show_add_options(self):
        Snackbar(text="Feature coming next: Add Routine/Exercise").open()

if __name__ == "__main__":
    GymTrackerApp().run()
