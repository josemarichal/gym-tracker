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
        
        # Ensure DB is initialized
        try:
            print("Initializing database...")
            DatabaseManager.init_db()
        except Exception as db_err:
            page.add(ft.Text(f"DB Init Error: {db_err}", color="red"))
            return

        page.title = "Gym Tracker Pro"
        page.theme_mode = ft.ThemeMode.DARK
        page.padding = 20
        

        def show_message(page, text):
            page.snack_bar = ft.SnackBar(content=ft.Text(text))
            page.snack_bar.open = True
            page.update()


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

        def open_add_routine_dialog(e):
            def close_dlg(e):
                dlg.open = False
                page.update()

            def save_routine(e):
                if not tf_name.value:
                    return
                try:
                    conn = DatabaseManager.get_connection()
                    cur = conn.cursor()
                    cur.execute("INSERT INTO routines (name) VALUES (?)", (tf_name.value,))
                    conn.commit()
                    conn.close()
                    dlg.open = False
                    page.update()
                    go_home()
                    show_message(page, f"Created {tf_name.value}!")
                except Exception as ex:
                   show_message(page, f"Error: {ex}") 

            tf_name = ft.TextField(label="Routine Name", hint_text="e.g. Push, Pull, Legs", autofocus=True)
            dlg = ft.AlertDialog(
                title=ft.Text("New Routine"),
                content=tf_name,
                actions=[
                    ft.TextButton("Cancel", on_click=close_dlg),
                    ft.TextButton("Create", on_click=save_routine),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.dialog = dlg
            dlg.open = True
            page.update()

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
                        elevation=5,
                        shape=ft.RoundedRectangleBorder(radius=15),
                        content=ft.Container(
                            gradient=ft.LinearGradient(
                                begin=ft.Alignment(-1, -1),
                                end=ft.Alignment(1, 1),
                                colors=[ft.Colors.BLUE_900, ft.Colors.PURPLE_900]
                            ),
                            border_radius=15,
                            padding=25,
                            height=100,
                            content=ft.Row([
                                ft.Text(r[1], size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                ft.Text(">", size=22, color=ft.Colors.WHITE54)
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            on_click=on_click_handler,
                            ink=True,
                            ink_color=ft.Colors.WHITE12
                        )
                    )
                )

            return ft.View(route=
                "/",
                controls=[
                    ft.AppBar(title=ft.Text("My Routines"), bgcolor="surfaceVariant"),
                    ft.Column(
                        controls=routine_controls,
                        scroll=ft.ScrollMode.AUTO
                    ),
                    ft.FloatingActionButton(
                        content=ft.Text("+", size=30), 
                        on_click=open_add_routine_dialog
                    ),
                ]
            )

        def routine_view(routine_id, routine_name):
            conn = DatabaseManager.get_connection()
            cursor = conn.cursor()
            
            def open_add_exercise_dialog(e):
                print(f"Opening add exercise dialog for routine {routine_id}")
                show_message(page, "Opening dialog...")
                def close_dlg(e):
                    dlg.open = False
                    page.update()

                def save_exercise(e):
                    if not tf_ex_name.value: return
                    try:
                         conn = DatabaseManager.get_connection()
                         cur = conn.cursor()
                         
                         # Check if exercise exists globally
                         res = cur.execute("SELECT id FROM exercises WHERE name=?", (tf_ex_name.value,)).fetchone()
                         if res:
                             new_ex_id = res[0]
                         else:
                             cur.execute("INSERT INTO exercises (name) VALUES (?)", (tf_ex_name.value,))
                             new_ex_id = cur.lastrowid
                         
                         # Link to routine
                         linked = cur.execute("SELECT * FROM exercise_routine WHERE exercise_id=? AND routine_id=?", (new_ex_id, routine_id)).fetchone()
                         if not linked:
                             cur.execute("INSERT INTO exercise_routine (exercise_id, routine_id) VALUES (?, ?)", (new_ex_id, routine_id))
                             conn.commit()
                             show_message(page, f"Added {tf_ex_name.value}!")
                         else:
                             show_message(page, "Already in routine")

                         conn.close()
                         dlg.open = False
                         
                         # Refresh the view manually since page.go won't trigger if route implies no change
                         page.views.pop()
                         page.views.append(routine_view(routine_id, routine_name))
                         page.update()
                         
                         show_message(page, f"Added {tf_ex_name.value}!")

                    except Exception as ex:
                        show_message(page, f"Error: {ex}")

                tf_ex_name = ft.TextField(label="Exercise Name", autofocus=True, on_submit=save_exercise)
                dlg = ft.AlertDialog(
                    title=ft.Text(f"Add to {routine_name}"),
                    content=tf_ex_name,
                    actions=[
                       ft.TextButton("Cancel", on_click=close_dlg),
                       ft.TextButton("Add", on_click=save_exercise) 
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                page.overlay.append(dlg)
                dlg.open = True
                page.update()

            query = """
                SELECT e.id, e.name 
                FROM exercises e
                JOIN exercise_routine er ON e.id = er.exercise_id
                WHERE er.routine_id = ?
                ORDER BY e.name
            """
            exercises = cursor.execute(query, (routine_id,)).fetchall()
            
            def refresh_view():
                 page.views.pop()
                 page.views.append(routine_view(routine_id, routine_name))
                 page.update()

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
                    ExerciseCard(ex_id, ex_name, last_log_text, routine_id, refresh_view).build()
                )

            # Add a backup button in the list
            exercise_controls.append(
                ft.Container(
                    content=ft.ElevatedButton("Add Exercise", on_click=open_add_exercise_dialog, width=200, bgcolor=ft.Colors.BLUE_900, color=ft.Colors.WHITE),
                    padding=20,
                    alignment=ft.Alignment(0, 0)
                )
            )

            conn.close()

            return ft.View(route=
                f"/routine/{routine_id}",
                controls=[
                    ft.AppBar(
                        title=ft.Text(routine_name), 
                        leading=ft.Container(content=ft.Text(" < Back", size=16, weight=ft.FontWeight.BOLD), on_click=lambda e: [page.views.pop(), page.update()], padding=10),
                        bgcolor="surfaceVariant"
                    ),
                    ft.Column(
                        controls=exercise_controls,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True
                    )
                ],
                floating_action_button=ft.FloatingActionButton(
                    content=ft.Text("+", size=30),
                    on_click=open_add_exercise_dialog
                )
            )
        
        # --- Custom Controls ---
        class ExerciseCard:
            def __init__(self, ex_id, name, log_text, routine_id, on_delete_callback):
                self.ex_id = ex_id
                self.name = name
                self.log_text = log_text
                self.routine_id = routine_id
                self.on_delete_callback = on_delete_callback
                
                self.txt_weight = ft.TextField(label="Lbs", width=80, keyboard_type=ft.KeyboardType.NUMBER)
                self.txt_reps = ft.TextField(label="Reps", width=80, keyboard_type=ft.KeyboardType.NUMBER)
                self.txt_sets = ft.TextField(label="Sets", width=80, keyboard_type=ft.KeyboardType.NUMBER)

            def delete_exercise(self, e):
                try:
                    conn = DatabaseManager.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM exercise_routine WHERE exercise_id=? AND routine_id=?", (self.ex_id, self.routine_id))
                    conn.commit()
                    conn.close()
                    show_message(e.page, f"Removed {self.name}")
                    if self.on_delete_callback:
                        self.on_delete_callback()
                except Exception as ex:
                    show_message(e.page, f"Error: {ex}")

            def save_log(self, e):
                if not self.txt_weight.value or not self.txt_reps.value or not self.txt_sets.value:
                    show_message(e.page, "Please fill all fields")
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
                    
                    show_message(e.page, f"Saved {self.name}!")
                    # Clear fields
                    self.txt_weight.value = ""
                    self.txt_reps.value = ""
                    self.txt_sets.value = ""
                    e.page.update()
                    
                except ValueError:
                    show_message(e.page, "Invalid numbers")

            def show_history(self, e):
                # Implement simple graph or history list here
                 show_message(e.page, "History graph coming soon!")

            def build(self):
                return ft.Card(
                    elevation=4,
                    shape=ft.RoundedRectangleBorder(radius=10),
                    content=ft.Container(
                        gradient=ft.LinearGradient(
                            begin=ft.Alignment(-1, -1),
                            end=ft.Alignment(1, 1),
                            colors=[ft.Colors.BLUE_GREY_900, ft.Colors.BLACK54]
                        ),
                        border_radius=10,
                        padding=15,
                        content=ft.Column([
                            ft.Row([
                                ft.Text(self.name, size=18, weight=ft.FontWeight.BOLD),
                                ft.Row([
                                    ft.Container(content=ft.Text("History", color=ft.Colors.BLUE_200), on_click=self.show_history, padding=5),
                                    ft.Container(content=ft.Text("X", color=ft.Colors.RED, weight=ft.FontWeight.BOLD), on_click=self.delete_exercise, padding=5),
                                ])
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            
                            ft.Text(self.log_text, size=12, italic=True, color=ft.Colors.WHITE70),
                            
                            ft.Container(height=10), # Spacer
                            
                            ft.Row([
                                self.txt_weight,
                                self.txt_reps,
                                self.txt_sets,
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            
                            ft.Container(height=10), # Spacer
                            
                            ft.ElevatedButton("Log Set", on_click=self.save_log, width=300, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
                        ])
                    )
                )

        # --- Routing ---
        # --- Routing ---
        def route_change(route):
            print(f"Route changed to: {page.route}")
            page.views.clear()
            
            try:
                # Always start with home view
                page.views.append(home_view())
                
                # Handle specific routes
                if page.route.startswith("/routine/"):
                     # Parse routine ID from route, e.g. /routine/1
                     try:
                         rout_id = int(page.route.split("/")[-1])
                         # We need to fetch the name again or pass it. 
                         # For now let's just fetch it from DB to be safe
                         conn = DatabaseManager.get_connection()
                         cur = conn.cursor()
                         res = cur.execute("SELECT name FROM routines WHERE id=?", (rout_id,)).fetchone()
                         conn.close()
                         if res:
                             page.views.append(routine_view(rout_id, res[0]))
                     except Exception as ex:
                         print(f"Error loading routine view: {ex}")
                         
            except Exception as e:
                print(f"Error in route_change: {e}")
                page.views.append(ft.View("/", [ft.Text(f"Error: {e}", color="red")]))
                
            page.update()

        def view_pop(view):
            page.views.pop()
            top_view = page.views[-1]
            page.go(top_view.route)

        page.on_route_change = route_change
        page.on_view_pop = view_pop
        
        # Initial navigation
        print(f"Initial calling of route_change with route: {page.route}")
        route_change(None)
        # page.go(page.route) # This might not trigger if already on route

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
