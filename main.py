import sqlite3
import logging
from datetime import datetime
import flet as ft
import os
import traceback

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO)

# --- Database Manager ---
class DatabaseManager:
    db_path = "weight_training.db"

    @staticmethod
    def set_db_path(path):
        DatabaseManager.db_path = path

    @staticmethod
    def get_connection():
        return sqlite3.connect(DatabaseManager.db_path)

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
        
        conn.commit()
        conn.close()

# --- App Logic ---

def main(page: ft.Page):
    try:
        # --- Platform Specific Setup ---
        # On Android/iOS, we must use a writeable document directory.
        if page.platform in [ft.PagePlatform.ANDROID, ft.PagePlatform.IOS]:
            # os.path.expanduser("~") commonly points to the app's writable usage home on P4A/mobile
            app_doc_dir = os.path.expanduser("~")
            db_file = os.path.join(app_doc_dir, "weight_training.db")
            DatabaseManager.set_db_path(db_file)
            print(f"Set DB path to: {db_file}")
        
        page.title = "Gym Tracker Pro"
        page.theme_mode = ft.ThemeMode.DARK
        page.padding = 20
        
        # Initialize DB
        DatabaseManager.init_db()

        # --- Navigation Functions ---
        def go_home(e=None):
            page.views.clear()
            page.views.append(home_view())
            page.update()

        def go_routine(routine_id, routine_name):
            page.views.append(routine_view(routine_id, routine_name))
            page.go(f"/routine/{routine_id}")
            page.update()

        # --- Views ---

        def home_view():
            conn = DatabaseManager.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM routines ORDER BY name")
            routines = cursor.fetchall()
            conn.close()

            routine_controls = []
            for r in routines:
                # Capture variable in closure using default arg
                def on_click_handler(e, r_id=r[0], r_name=r[1]):
                    go_routine(r_id, r_name)

                routine_controls.append(
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.Text(r[1], size=20, weight=ft.FontWeight.BOLD),
                                ft.Icon(ft.icons.CHEVRON_RIGHT, color=ft.colors.BLUE_200)
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            padding=20,
                            on_click=on_click_handler
                        )
                    )
                )

            return ft.View(
                "/",
                controls=[
                    ft.AppBar(title=ft.Text("My Routines"), bgcolor=ft.colors.SURFACE_VARIANT),
                    ft.Column(
                        controls=routine_controls,
                        scroll=ft.ScrollMode.AUTO
                    ),
                    ft.FloatingActionButton(
                        icon=ft.icons.ADD, 
                        on_click=lambda e: page.open(ft.SnackBar(ft.Text("Add Routine coming next!")))
                    ),
                ]
            )

        def routine_view(routine_id, routine_name):
            conn = DatabaseManager.get_connection()
            cursor = conn.cursor()
            
            query = """
                SELECT e.id, e.name 
                FROM exercises e
                JOIN exercise_routine er ON e.id = er.exercise_id
                WHERE er.routine_id = ?
                ORDER BY e.name
            """
            exercises = cursor.execute(query, (routine_id,)).fetchall()
            
            exercise_controls = []
            for ex in exercises:
                ex_id, ex_name = ex[0], ex[1]
                
                # Get last log
                last_log = cursor.execute("""
                    SELECT weight, reps, sets, date FROM workout_log 
                    WHERE exercise_id = ? 
                    ORDER BY date DESC LIMIT 1
                """, (ex_id,)).fetchone()
                
                last_log_text = "New Exercise"
                if last_log:
                    last_log_text = f"Last: {last_log[2]}x{last_log[1]} @ {last_log[0]}lbs"

                exercise_controls.append(
                    ExerciseCard(ex_id, ex_name, last_log_text, routine_id).build()
                )

            conn.close()

            return ft.View(
                f"/routine/{routine_id}",
                controls=[
                    ft.AppBar(
                        title=ft.Text(routine_name), 
                        leading=ft.IconButton(ft.icons.ARROW_BACK, on_click=lambda e: page.pop()),
                        bgcolor=ft.colors.SURFACE_VARIANT
                    ),
                    ft.Column(
                        controls=exercise_controls,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True
                    )
                ]
            )
        
        # --- Custom Controls ---
        class ExerciseCard:
            def __init__(self, ex_id, name, log_text, routine_id):
                self.ex_id = ex_id
                self.name = name
                self.log_text = log_text
                self.routine_id = routine_id
                
                self.txt_weight = ft.TextField(label="Lbs", width=80, keyboard_type=ft.KeyboardType.NUMBER)
                self.txt_reps = ft.TextField(label="Reps", width=80, keyboard_type=ft.KeyboardType.NUMBER)
                self.txt_sets = ft.TextField(label="Sets", width=80, keyboard_type=ft.KeyboardType.NUMBER)

            def save_log(self, e):
                if not self.txt_weight.value or not self.txt_reps.value or not self.txt_sets.value:
                    e.page.open(ft.SnackBar(ft.Text("Please fill all fields")))
                    return

                try:
                    weight = float(self.txt_weight.value)
                    reps = int(self.txt_reps.value)
                    sets = int(self.txt_sets.value)
                    
                    conn = DatabaseManager.get_connection()
                    cursor = conn.cursor()
                    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    cursor.execute("""
                        INSERT INTO workout_log (exercise_id, routine_id, date, weight, reps, sets)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (self.ex_id, self.routine_id, date_str, weight, reps, sets))
                    conn.commit()
                    conn.close()
                    
                    e.page.open(ft.SnackBar(ft.Text(f"Saved {self.name}!")))
                    # Clear fields
                    self.txt_weight.value = ""
                    self.txt_reps.value = ""
                    self.txt_sets.value = ""
                    e.page.update()
                    
                except ValueError:
                    e.page.open(ft.SnackBar(ft.Text("Invalid numbers")))

            def show_history(self, e):
                # Implement simple graph or history list here
                 e.page.open(ft.SnackBar(ft.Text("History graph coming soon!")))

            def build(self):
                return ft.Card(
                    content=ft.Container(
                        padding=10,
                        content=ft.Column([
                            ft.Row([
                                ft.Text(self.name, size=18, weight=ft.FontWeight.BOLD),
                                ft.IconButton(ft.icons.SHOW_CHART, on_click=self.show_history)
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            
                            ft.Text(self.log_text, size=12, italic=True),
                            
                            ft.Row([
                                self.txt_weight,
                                self.txt_reps,
                                self.txt_sets,
                            ]),
                            
                            ft.ElevatedButton("Log Set", on_click=self.save_log, width=300)
                        ])
                    )
                )

        # --- Routing ---
        def route_change(route):
            page.views.clear()
            page.views.append(home_view())
            if page.route == "/routine":
                pass 
            page.update()

        def view_pop(view):
            page.views.pop()
            top_view = page.views[-1]
            page.go(top_view.route)

        page.on_route_change = route_change
        page.on_view_pop = view_pop
        
        page.go(page.route)

    except Exception as e:
        page.clean()
        page.add(
            ft.Column([
                ft.Text("Initialization Error:", color=ft.colors.RED, size=20, weight=ft.FontWeight.BOLD),
                ft.Text(str(e), color=ft.colors.RED),
                ft.Text("Traceback:", weight=ft.FontWeight.BOLD, color=ft.colors.RED),
                ft.Text(traceback.format_exc(), color=ft.colors.RED, font_family="monospace")
            ], scroll=ft.ScrollMode.AUTO)
        )
        page.update()

ft.app(target=main)
