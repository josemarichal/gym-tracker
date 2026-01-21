import os
import sys
import sqlite3
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.properties import ObjectProperty
from kivy.factory import Factory
from datetime import datetime, timedelta
import logging
from kivy.utils import platform

logging.basicConfig(level=logging.INFO)  # INFO is usually sufficient for release

# --- Platform-specific configuration ---
if platform == 'android':
    from android.permissions import request_permissions, Permission
    from android.storage import primary_external_storage_path
    
    def check_permissions():
        request_permissions([
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.READ_EXTERNAL_STORAGE
        ])
else:
    def check_permissions():
        pass  # No permissions needed on desktop

# Configure data paths based on platform
if platform == 'android':
    try:
        # Use app-specific storage on Android
        from android.storage import app_storage_path
        base_path = app_storage_path()
        logging.info(f"Using Android app storage path: {base_path}")
    except Exception as e:
        # Fallback to external storage
        try:
            base_path = primary_external_storage_path()
            logging.info(f"Using Android external storage path: {base_path}")
        except Exception as e:
            logging.error(f"Failed to get Android storage paths: {e}")
            base_path = os.path.dirname(os.path.abspath(__file__))
else:
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # Use this directory if running as a packaged app
        base_path = sys._MEIPASS
    except Exception:
        # Otherwise, use the directory of the script file
        base_path = os.path.abspath(".")

DB_FILE = os.path.join(base_path, "weight_training.db")
logging.info(f"Database file path: {DB_FILE}")

# --- Database Functions ---

def get_db_connection():
    """Establishes and returns a database connection and cursor."""
    try:
        conn = sqlite3.connect(DB_FILE)
        # Return row objects that can be accessed by column name
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        return conn, cursor
    except sqlite3.Error as e:
        logging.error(f"Database connection error: {e}")
        raise  # Re-raise the exception to be handled by the caller

def close_db_connection(conn):
    """Closes the database connection."""
    if conn:
        conn.commit()
        conn.close()

def init_db():
    """Initializes the database schema if tables don't exist."""
    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        logging.debug("Initializing database schema...")

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

        logging.info("Database schema initialized or verified successfully.")
    except sqlite3.Error as e:
        logging.error(f"Database initialization error: {e}")
    finally:
        close_db_connection(conn)

def check_and_update_db_schema():
    """Checks for and adds missing columns to the workout_log table."""
    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        logging.debug("Checking database schema...")

        cursor.execute("PRAGMA table_info(workout_log)")
        columns = [column['name'] for column in cursor.fetchall()]

        updated = False
        if "routine_id" not in columns:
            cursor.execute("ALTER TABLE workout_log ADD COLUMN routine_id INTEGER REFERENCES routines(id)")
            logging.info("Added 'routine_id' column to workout_log table.")
            updated = True

        if "sets" not in columns:
            # Add sets column with a default value if it's missing
            cursor.execute("ALTER TABLE workout_log ADD COLUMN sets INTEGER DEFAULT 1 NOT NULL")
            logging.info("Added 'sets' column to workout_log table.")
            updated = True

        if updated:
            logging.info("Database schema updated.")
        else:
            logging.debug("Database schema is up-to-date.")

    except sqlite3.Error as e:
        logging.error(f"Schema update error: {e}")
    finally:
        close_db_connection(conn)


# --- Kivy Main Widget ---

class WeightTracker(BoxLayout):
    # Use ObjectProperty for easier access from kv lang if needed,
    # and better management than direct self.ids access early on.
    screen_manager = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = []  # Initialize empty list for workout data
        # Schedule loading and initial calculations after the UI is built
        Clock.schedule_once(self.post_init)

    # --- MODIFIED post_init ---
    def post_init(self, dt):
        """Tasks to run after the UI elements are built and accessible."""
        logging.debug("Post-init started.")
        # Check Android permissions first
        if platform == 'android':
            check_permissions()
        
        # Initialize database after permissions are granted
        init_db()
        check_and_update_db_schema()
        
        # Assign the screen manager from ids
        self.screen_manager = self.ids.screen_manager
        if not self.screen_manager:
             logging.error("ScreenManager not found in ids!")
             return # Cannot proceed without screen manager

        self.load_exercises()
        self.load_routines() # This now populates the new spinner too
        self.load_workout_data()  # Load workout log data
        self.calculate_summary_stats()  # Calculate initial stats
        logging.debug("Post-init finished.")


        # Set default spinner text if lists are not empty
        # Main Screen Spinners
        if 'exercise_spinner' in self.ids and self.ids.exercise_spinner.values:
            self.ids.exercise_spinner.text = self.ids.exercise_spinner.values[0]
        if 'routine_spinner' in self.ids and self.ids.routine_spinner.values:
            self.ids.routine_spinner.text = self.ids.routine_spinner.values[0]
        # Association Screen Spinners
        if 'exercise_spinner_associate' in self.ids and self.ids.exercise_spinner_associate.values:
            self.ids.exercise_spinner_associate.text = self.ids.exercise_spinner_associate.values[0]
        if 'routine_spinner_associate' in self.ids and self.ids.routine_spinner_associate.values:
            self.ids.routine_spinner_associate.text = self.ids.routine_spinner_associate.values[0]
        # View Routine Exercises Screen Spinner (NEW)
        if 'routine_spinner_view' in self.ids and self.ids.routine_spinner_view.values:
            self.ids.routine_spinner_view.text = self.ids.routine_spinner_view.values[0]
            # Trigger initial load for the view screen if a routine is selected
            self.update_routine_exercises_display()
        elif 'routine_spinner_view' in self.ids:
             # Ensure default text if no routines exist yet
             self.ids.routine_spinner_view.text = "Select Routine"

    # --- Database Helpers (Unchanged) ---
    def _fetch_from_db(self, query, params=()):
        """Helper to fetch data from the database."""
        conn, cursor = None, None
        try:
            conn, cursor = get_db_connection()
            cursor.execute(query, params)
            return cursor.fetchall()
        except sqlite3.Error as e:
            logging.error(f"Error fetching data: {e}")
            self.update_status(f"DB Error: {e}", error=True)
            return []
        finally:
            close_db_connection(conn)

    def _execute_db(self, query, params=()):
        """Helper to execute insert/update/delete operations."""
        conn, cursor = None, None
        try:
            conn, cursor = get_db_connection()
            cursor.execute(query, params)
            last_id = cursor.lastrowid
            close_db_connection(conn)  # Commit happens in close_db_connection
            return last_id  # Return last inserted ID if needed
        except sqlite3.IntegrityError as e:
            logging.warning(f"Database integrity error: {e}")
            raise  # Re-raise to be handled by caller (e.g., duplicate entry)
        except sqlite3.Error as e:
            logging.error(f"Database execution error: {e}")
            self.update_status(f"DB Error: {e}", error=True)
            # Don't close connection here if error occurs before commit
            if conn:
                conn.rollback()  # Rollback changes on error
                conn.close()
            return None

    def _get_id_from_name(self, table_name, item_name):
        """Gets the ID of an item (exercise or routine) by its name."""
        query = f"SELECT id FROM {table_name} WHERE name = ?"
        result = self._fetch_from_db(query, (item_name,))
        if result:
            return result[0]['id']  # Access by column name due to row_factory
        return None

    # --- Loading Methods ---
    def load_exercises(self):
        """Loads exercises from DB and updates relevant spinners."""
        exercises = self._fetch_from_db("SELECT name FROM exercises ORDER BY name")
        exercise_names = [row['name'] for row in exercises]

        spinners_to_update = [
            self.ids.get('exercise_spinner'),
            self.ids.get('exercise_spinner_associate')
        ]

        for spinner in spinners_to_update:
            if spinner: # Check if spinner exists in ids
                spinner.values = exercise_names
                # Reset text if current text is no longer valid or if it's the default
                current_text = spinner.text
                default_text = "Select Exercise"
                if current_text == default_text or current_text not in exercise_names:
                    spinner.text = default_text if not exercise_names else exercise_names[0]

        logging.debug(f"Loaded exercises: {exercise_names}")

    # --- MODIFIED load_routines ---
    def load_routines(self):
        """Loads routines from DB and updates relevant spinners."""
        routines = self._fetch_from_db("SELECT name FROM routines ORDER BY name")
        routine_names = [row['name'] for row in routines]

        # Update all relevant spinners
        spinners_to_update = [
            self.ids.get('routine_spinner'),
            self.ids.get('routine_spinner_associate'),
            self.ids.get('routine_spinner_view') # NEW: Add the view screen spinner
        ]

        for spinner in spinners_to_update:
            if spinner: # Check if spinner exists in ids
                spinner.values = routine_names
                # Reset text if current text is no longer valid or if it's the default
                current_text = spinner.text
                default_text = "Select Routine"
                if current_text == default_text or current_text not in routine_names:
                    spinner.text = default_text if not routine_names else routine_names[0]

        logging.debug(f"Loaded routines: {routine_names}")

    def load_workout_data(self):
        """Loads workout log data into a list of dictionaries."""
        self.data = []  # Reset data list
        try:
            logging.debug("Loading workout data...")
            rows = self._fetch_from_db(
                "SELECT id, exercise_id, routine_id, date, weight, reps, sets FROM workout_log"
            )

            for row in rows:
                # Convert sqlite3.Row to regular dict
                entry = dict(row)

                # Parse date string to datetime object
                try:
                    entry['date'] = datetime.strptime(entry['date'], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    # Try alternative date format if the first one fails
                    try:
                        entry['date'] = datetime.strptime(entry['date'], "%Y-%m-%d")
                    except ValueError as e:
                        logging.warning(f"Skipping entry with invalid date: {entry['date']}, error: {e}")
                        continue

                self.data.append(entry)

            # Sort data by date
            self.data.sort(key=lambda x: x['date'])
            logging.info(f"Loaded {len(self.data)} workout log entries.")
        except Exception as e:
            logging.error(f"Error loading workout data: {e}", exc_info=True)
            self.update_status(f"Error loading logs: {e}", error=True)
            self.data = []  # Ensure data is empty list on error

    # --- UI Update Methods (Unchanged except for status label check) ---
    def update_status(self, message, error=False):
        """Updates the status label text and color."""
        # Use .get() for safer access to ids dictionary
        status_label = self.ids.get('status_label')
        if status_label:
            status_label.text = message
            status_label.color = (1, 0, 0, 1) if error else (0, 0.7, 0, 1) # Adjusted green
            if error:
                logging.error(f"Status Update (Error): {message}")
            else:
                logging.info(f"Status Update: {message}")
        else:
             logging.warning(f"Status label not available. Message: {message}")

    # --- Action/Saving Methods (Unchanged) ---
    def save_data(self):
        """Saves the current workout log entry."""
        exercise_name = self.ids.exercise_spinner.text.strip()
        routine_name = self.ids.routine_spinner.text.strip()
        weight_input = self.ids.weight_input.text.strip()
        reps_input = self.ids.reps_input.text.strip()
        sets_input = self.ids.sets_input.text.strip()

        # --- Input Validation ---
        if not exercise_name or exercise_name == "Select Exercise":
            self.update_status("Please select an exercise.", error=True)
            return
        if not routine_name or routine_name == "Select Routine":
            self.update_status("Please select a routine.", error=True)
            return
        if not weight_input:
            self.update_status("Weight cannot be empty.", error=True)
            return
        if not reps_input:
            self.update_status("Reps cannot be empty.", error=True)
            return
        if not sets_input:
            self.update_status("Sets cannot be empty.", error=True)
            return

        try:
            weight = float(weight_input)
            reps = int(reps_input)
            sets = int(sets_input)
            if weight <= 0 or reps <= 0 or sets <= 0:
                 raise ValueError("Weight, reps, and sets must be positive numbers.")
        except ValueError as e:
            self.update_status(f"Invalid input: {e}", error=True)
            return

        # --- Get IDs ---
        exercise_id = self._get_id_from_name("exercises", exercise_name)
        routine_id = self._get_id_from_name("routines", routine_name)

        if exercise_id is None:
             self.update_status(f"Exercise '{exercise_name}' not found in DB.", error=True)
             return
        if routine_id is None:
             self.update_status(f"Routine '{routine_name}' not found in DB.", error=True)
             return

        # --- Save to DB ---
        try:
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            query = '''INSERT INTO workout_log (exercise_id, routine_id, date, weight, reps, sets)
                       VALUES (?, ?, ?, ?, ?, ?)'''
            params = (exercise_id, routine_id, current_date, weight, reps, sets)
            self._execute_db(query, params)

            self.update_status(f"Saved: {exercise_name} ({sets}x{reps} @ {weight}lbs)")
            self.load_workout_data()  # Reload data
            self.clear_inputs()
            self.calculate_summary_stats()  # Recalculate stats for the current selection

        except sqlite3.Error as e:
            self.update_status(f"Database save error: {e}", error=True)
        except Exception as e:
             self.update_status(f"An unexpected error occurred: {e}", error=True)

    def clear_inputs(self):
        """Clears the weight, reps, and sets input fields."""
        if not hasattr(self, 'ids'):
            return
        if 'weight_input' in self.ids: self.ids.weight_input.text = ''
        if 'reps_input' in self.ids: self.ids.reps_input.text = ''
        if 'sets_input' in self.ids: self.ids.sets_input.text = ''
        # Optionally reset spinners, or leave them as they are
        # if 'exercise_spinner' in self.ids: self.ids.exercise_spinner.text = "Select Exercise"
        # if 'routine_spinner' in self.ids: self.ids.routine_spinner.text = "Select Routine"

    def calculate_summary_stats(self, *args):
        """Calculates and displays progress stats for the selected exercise/routine."""
        if not hasattr(self, 'data') or not self.data:
            self.clear_stats_display()
            logging.debug("Stats calculation skipped: No data.")
            return
        if not hasattr(self, 'ids'):
            logging.warning("Stats calculation skipped: UI IDs not available.")
            return

        # Get currently selected exercise and routine from the main screen
        exercise_name = self.ids.get('exercise_spinner', Factory.Spinner()).text # Use Factory default if not found
        routine_name = self.ids.get('routine_spinner', Factory.Spinner()).text

        last_workout_label = self.ids.get('last_workout_details')

        if not exercise_name or exercise_name == "Select Exercise" or \
           not routine_name or routine_name == "Select Routine":
            self.clear_stats_display()
            logging.debug("Stats calculation skipped: Exercise or Routine not selected.")
            return

        exercise_id = self._get_id_from_name("exercises", exercise_name)
        routine_id = self._get_id_from_name("routines", routine_name)

        if exercise_id is None or routine_id is None:
            self.clear_stats_display()
            logging.debug("Stats calculation skipped: Could not find ID for selected exercise/routine.")
            return

        try:
            # Filter data for the SPECIFIC selected exercise and routine
            filtered_data = [
                entry for entry in self.data
                if entry.get('exercise_id') == exercise_id and entry.get('routine_id') == routine_id
            ]

            if not filtered_data:
                self.clear_stats_display(message="No history for this combination.")
                logging.debug(f"No data found for Exercise ID {exercise_id} and Routine ID {routine_id}")
                return

            # Ensure data is sorted by date
            filtered_data.sort(key=lambda x: x['date'])

            filtered_data.sort(key=lambda x: x['date'])

            # --- NEW: Get Last Workout Details ---
            last_entry = filtered_data[-1] # Get the most recent entry
            last_weight = last_entry.get('weight', 'N/A')
            last_reps = last_entry.get('reps', 'N/A')
            last_sets = last_entry.get('sets', 'N/A')
            last_date = last_entry.get('date') # Get the date object
            last_date_str = last_date.strftime('%Y-%m-%d') if last_date else 'N/A' # Format date

            if last_workout_label:
                last_workout_label.text = (
                    f"Last Recorded ({last_date_str}): "
                    f"{last_sets} sets x {last_reps} reps @ {last_weight} lbs"
                )

            latest_date = max(entry['date'] for entry in filtered_data)

            # Helper function to get change over a period for a specific metric
            def get_change(metric, days):
                start_date = latest_date - timedelta(days=days)
                # Select data within the date range
                period_data = [entry for entry in filtered_data if entry['date'] >= start_date]

                if len(period_data) < 2:
                    return None  # Need at least two data points for a change

                # Get the value from the earliest and latest record IN THE PERIOD
                first_val = period_data[0].get(metric)
                last_val = period_data[-1].get(metric)

                # Check if values are valid numbers before subtracting
                if isinstance(first_val, (int, float)) and isinstance(last_val, (int, float)):
                    return last_val - first_val
                else:
                    logging.warning(f"Invalid data type for metric '{metric}' in change calculation.")
                    return None # Cannot calculate change if data is not numeric

            # Update Weight changes
            wc1m = get_change('weight', 30)
            if 'weight_change_1m' in self.ids: self.ids.weight_change_1m.text = f"{wc1m:+.1f} lbs" if wc1m is not None else "N/A"
            wc3m = get_change('weight', 90)
            if 'weight_change_3m' in self.ids: self.ids.weight_change_3m.text = f"{wc3m:+.1f} lbs" if wc3m is not None else "N/A"
            wc6m = get_change('weight', 180)
            if 'weight_change_6m' in self.ids: self.ids.weight_change_6m.text = f"{wc6m:+.1f} lbs" if wc6m is not None else "N/A"

            # Update Reps changes
            rc1m = get_change('reps', 30)
            if 'reps_change_1m' in self.ids: self.ids.reps_change_1m.text = f"{rc1m:+.0f}" if rc1m is not None else "N/A"
            rc3m = get_change('reps', 90)
            if 'reps_change_3m' in self.ids: self.ids.reps_change_3m.text = f"{rc3m:+.0f}" if rc3m is not None else "N/A"
            rc6m = get_change('reps', 180)
            if 'reps_change_6m' in self.ids: self.ids.reps_change_6m.text = f"{rc6m:+.0f}" if rc6m is not None else "N/A"

            # Update Sets changes
            sc1m = get_change('sets', 30)
            if 'sets_change_1m' in self.ids: self.ids.sets_change_1m.text = f"{sc1m:+.0f}" if sc1m is not None else "N/A"
            sc3m = get_change('sets', 90)
            if 'sets_change_3m' in self.ids: self.ids.sets_change_3m.text = f"{sc3m:+.0f}" if sc3m is not None else "N/A"
            sc6m = get_change('sets', 180)
            if 'sets_change_6m' in self.ids: self.ids.sets_change_6m.text = f"{sc6m:+.0f}" if sc6m is not None else "N/A"

            logging.debug(f"Stats calculated for {exercise_name} / {routine_name}")

        except Exception as e:
            logging.error(f"Error calculating stats: {e}", exc_info=True)  # Log traceback
            self.update_status(f"Error calculating stats: {e}", error=True)
            self.clear_stats_display(message="Error")

    def clear_stats_display(self, message="N/A"):
        """Resets all stat labels to a default message."""
        if not hasattr(self, 'ids'): return
        for metric in ['weight', 'reps', 'sets']:
            for period in ['1m', '3m', '6m']:
                label_id = f"{metric}_change_{period}"
                if label_id in self.ids:
                    self.ids[label_id].text = message

        last_workout_label = self.ids.get('last_workout_details')
        if last_workout_label:
            # Use a specific message for this one if the general 'message' is "Error"
            default_text = "Last Recorded: N/A" if message != "Error" else "Last Recorded: Error"
            last_workout_label.text = default_text

    def save_new_exercise(self):
        """Saves a new exercise entered on the 'add_exercise' screen."""
        exercise_name_input = self.ids.get('exercise_name_input')
        if not exercise_name_input:
            self.update_status("UI Error: Exercise input not found.", error=True)
            return

        exercise_name = exercise_name_input.text.strip()
        if not exercise_name:
            self.update_status("Exercise name cannot be empty!", error=True)
            return

        try:
            query = "INSERT INTO exercises (name) VALUES (?)"
            self._execute_db(query, (exercise_name,))
            self.load_exercises()  # Reload exercises in spinners
            exercise_name_input.text = ""  # Clear input
            if self.screen_manager: self.screen_manager.current = 'main'
            self.update_status(f"Exercise '{exercise_name}' added successfully.")
        except sqlite3.IntegrityError:
            self.update_status(f"Exercise '{exercise_name}' already exists.", error=True)
        except Exception as e:
             self.update_status(f"Error adding exercise: {e}", error=True)

    def save_new_routine(self):
        """Saves a new routine entered on the 'add_routine' screen."""
        routine_name_input = self.ids.get('routine_name_input')
        if not routine_name_input:
            self.update_status("UI Error: Routine input not found.", error=True)
            return

        routine_name = routine_name_input.text.strip()
        if not routine_name:
            self.update_status("Routine name cannot be empty!", error=True)
            return

        try:
            query = "INSERT INTO routines (name) VALUES (?)"
            self._execute_db(query, (routine_name,))
            self.load_routines()  # Reload routines in spinners
            routine_name_input.text = ""  # Clear input
            if self.screen_manager: self.screen_manager.current = 'main'
            self.update_status(f"Routine '{routine_name}' added successfully.")
        except sqlite3.IntegrityError:
            self.update_status(f"Routine '{routine_name}' already exists.", error=True)
        except Exception as e:
             self.update_status(f"Error adding routine: {e}", error=True)

    def associate_exercise_with_routine(self):
        """Associates the selected exercise with the selected routine."""
        exercise_spinner = self.ids.get('exercise_spinner_associate')
        routine_spinner = self.ids.get('routine_spinner_associate')

        if not exercise_spinner or not routine_spinner:
            self.update_status("UI Error: Association spinners not found.", error=True)
            return

        exercise_name = exercise_spinner.text.strip()
        routine_name = routine_spinner.text.strip()

        if not exercise_name or exercise_name == "Select Exercise":
            self.update_status("Please select an exercise to associate.", error=True)
            return
        if not routine_name or routine_name == "Select Routine":
            self.update_status("Please select a routine to associate.", error=True)
            return

        exercise_id = self._get_id_from_name("exercises", exercise_name)
        routine_id = self._get_id_from_name("routines", routine_name)

        if exercise_id is None or routine_id is None:
            self.update_status("Selected exercise or routine not found.", error=True)
            return

        try:
            query = "INSERT INTO exercise_routine (exercise_id, routine_id) VALUES (?, ?)"
            self._execute_db(query, (exercise_id, routine_id))
            if self.screen_manager: self.screen_manager.current = 'main'
            self.update_status(f"Associated '{exercise_name}' with '{routine_name}'.")
        except sqlite3.IntegrityError:
            self.update_status(f"'{exercise_name}' is already associated with '{routine_name}'.", error=True)
        except Exception as e:
            self.update_status(f"Error associating: {e}", error=True)

    # --- NEW Methods for Viewing Routine Exercises ---

    def load_exercises_for_routine(self, routine_name):
        """Fetches the names of exercises associated with a given routine name."""
        if not routine_name or routine_name == "Select Routine":
            return [] # Return empty list if no valid routine is selected

        routine_id = self._get_id_from_name("routines", routine_name)
        if routine_id is None:
            logging.warning(f"Could not find ID for routine: {routine_name}")
            return [] # Routine not found in DB

        query = """
            SELECT e.name
            FROM exercises e
            JOIN exercise_routine er ON e.id = er.exercise_id
            WHERE er.routine_id = ?
            ORDER BY e.name
        """
        try:
            results = self._fetch_from_db(query, (routine_id,))
            exercise_names = [row['name'] for row in results]
            logging.debug(f"Exercises for routine '{routine_name}' (ID: {routine_id}): {exercise_names}")
            return exercise_names
        except Exception as e:
            logging.error(f"Error fetching exercises for routine '{routine_name}': {e}")
            self.update_status(f"Error loading exercises for routine: {e}", error=True)
            return [] # Return empty on error

    def update_routine_exercises_display(self, *args):
        """Updates the label on the 'view_routine_exercises' screen."""
        spinner = self.ids.get('routine_spinner_view')
        display_label = self.ids.get('routine_exercises_display')

        if not spinner or not display_label:
             logging.warning("Required widgets for viewing routine exercises not found in ids.")
             self.update_status("UI Error: Cannot update routine view.", error=True)
             return

        selected_routine = spinner.text
        # display_label = self.ids.routine_exercises_display # Already got it above

        if not selected_routine or selected_routine == "Select Routine":
            display_label.text = "Select a routine above to see its exercises."
            # Reset height in case it was previously large
            display_label.height = display_label.texture_size[1]
            return

        exercise_names = self.load_exercises_for_routine(selected_routine)

        if not exercise_names:
            display_label.text = f"No exercises are currently associated with the '{selected_routine}' routine."
        else:
            # Format the list for display
            display_text = f"Exercises in '{selected_routine}':\n\n" + "\n".join(f"- {name}" for name in exercise_names)
            display_label.text = display_text

        # Adjust texture_size for proper text wrapping in the label within ScrollView
        display_label.texture_update() # Force texture update
        # Set height based on text content for ScrollView
        display_label.height = display_label.texture_size[1]

# --- Kivy Language String ---
# Added on_text bindings to main spinners to trigger recalculation
# Added default text to spinners
# Added size_hint_min_x to prevent labels/inputs becoming too small
# Added hint_text to TextInputs
# Add this import at the top of your python file if not already there
# (Though Builder.load_string usually handles imports defined in kv)
# from kivy.metrics import dp # Not strictly needed if only used in kv

# --- Kivy Language String ---
# Add the dp import for kv
# Wrap the main screen's content in a ScrollView
Builder.load_string('''
#:import Factory kivy.factory.Factory
#:import dp kivy.metrics.dp 

<StatusLabel@Label>: # Custom Label for Status
    size_hint_y: None
    height: dp(30) # Use dp
    halign: 'center'
    valign: 'middle'

<InputLabel@Label>: # Custom Label for Inputs
    size_hint_x: 0.4
    text_size: self.width, None
    halign: 'right'
    valign: 'middle'
    padding_x: dp(10) # Use dp

<ValueLabel@Label>: # Custom Label for Stat Values
    size_hint_x: 0.25
    halign: 'center'
    valign: 'middle'

<HeaderLabel@Label>:
    font_size: '20sp'
    size_hint_y: None
    height: dp(40) # Use dp
    bold: True

<NavButton@Button>:
    size_hint_y: None
    height: dp(50) # Use dp
    font_size: '16sp'
    # Make buttons larger on Android for easier touch
    padding: dp(10), dp(10)

<WeightTracker>:
    orientation: 'vertical'
    padding: dp(10) # Use dp
    spacing: dp(10) # Use dp
    screen_manager: screen_manager

    ScreenManager:
        id: screen_manager
        size_hint: 1, 0.9 # Keep this ratio, it seems reasonable

        Screen:
            name: 'main'
            # WRAP the content in a ScrollView
            ScrollView:
                do_scroll_x: False # Disable horizontal scrolling
                bar_width: dp(10) # Make scrollbar visible

                # This BoxLayout goes INSIDE the ScrollView
                # It needs size_hint_y: None and height: self.minimum_height
                BoxLayout:
                    orientation: 'vertical'
                    spacing: dp(8) # Use dp
                    padding: dp(10) # Add padding inside the scroll area
                    size_hint_y: None # CRITICAL: Tell ScrollView content height is fixed
                    height: self.minimum_height # CRITICAL: Set height based on children

                    # --- All the original content of the main screen's BoxLayout goes here ---
                    # --- Use dp for heights and spacing ---
                    HeaderLabel:
                        text: 'Log Workout'

                    GridLayout:
                        cols: 2
                        spacing: dp(5)
                        size_hint_y: None
                        height: dp(50) # Increased height for Android touch

                        InputLabel:
                            text: 'Exercise:'
                        Spinner:
                            id: exercise_spinner
                            text: "Select Exercise"
                            values: []
                            on_text: root.calculate_summary_stats()
                            # Make spinner more touch-friendly
                            font_size: '16sp'
                            option_cls: "SpinnerOption"

                    GridLayout:
                        cols: 2
                        spacing: dp(5)
                        size_hint_y: None
                        height: dp(50)

                        InputLabel:
                            text: 'Routine:'
                        Spinner:
                            id: routine_spinner
                            text: "Select Routine"
                            values: []
                            on_text: root.calculate_summary_stats()
                            font_size: '16sp'
                            option_cls: "SpinnerOption"

                    GridLayout:
                        cols: 2
                        spacing: dp(5)
                        size_hint_y: None
                        height: dp(50)

                        InputLabel:
                            text: 'Weight (lbs):'
                        TextInput:
                            id: weight_input
                            multiline: False
                            input_filter: 'float'
                            hint_text: 'e.g., 135.5'
                            write_tab: False
                            font_size: '16sp'
                            padding: dp(10), dp(10)

                    GridLayout:
                        cols: 2
                        spacing: dp(5)
                        size_hint_y: None
                        height: dp(50)

                        InputLabel:
                            text: 'Reps:'
                        TextInput:
                            id: reps_input
                            multiline: False
                            input_filter: 'int'
                            hint_text: 'e.g., 10'
                            write_tab: False
                            font_size: '16sp'
                            padding: dp(10), dp(10)

                    GridLayout:
                        cols: 2
                        spacing: dp(5)
                        size_hint_y: None
                        height: dp(50)

                        InputLabel:
                            text: 'Sets:'
                        TextInput:
                            id: sets_input
                            multiline: False
                            input_filter: 'int'
                            hint_text: 'e.g., 3'
                            write_tab: False
                            font_size: '16sp'
                            padding: dp(10), dp(10)

                    BoxLayout:
                        orientation: 'horizontal'
                        size_hint_y: None
                        height: dp(60)
                        spacing: dp(10)

                        Button:
                            text: 'Save Entry'
                            font_size: '16sp'
                            on_press: root.save_data()
                        Button:
                            text: 'Clear Inputs'
                            font_size: '16sp'
                            on_press: root.clear_inputs()

                    # Progress Section
                    Label:
                        text: "Progress for Selected Exercise/Routine"
                        size_hint_y: None
                        height: dp(30)
                        font_size: '16sp'
                        italic: True

                    # --- LABEL FOR LAST WORKOUT DETAILS ---
                    Label:
                        id: last_workout_details
                        text: "Last Recorded: N/A"
                        size_hint_y: None
                        height: self.texture_size[1] + dp(5)
                        font_size: '14sp'
                        color: 0.8, 0.8, 0.8, 1
                        halign: 'center'
                        valign: 'middle'
                        padding_y: dp(5)
                    
                    GridLayout:
                        cols: 4
                        size_hint_y: None
                        height: dp(100) # Increased height for better touch
                        spacing: dp(2)

                        # Header Row
                        Label:
                            text: 'Change Over:'
                            bold: True
                            size_hint_x: 0.25
                            font_size: '14sp'
                        Label:
                            text: '1 Month'
                            bold: True
                            size_hint_x: 0.25
                            font_size: '14sp'
                        Label:
                            text: '3 Months'
                            bold: True
                            size_hint_x: 0.25
                            font_size: '14sp'
                        Label:
                            text: '6 Months'
                            bold: True
                            size_hint_x: 0.25
                            font_size: '14sp'

                        # Weight Row
                        Label:
                            text: 'Weight Δ:'
                            halign:'right'
                            padding_x: dp(5)
                            size_hint_x: 0.25
                            font_size: '14sp'
                        ValueLabel:
                            id: weight_change_1m
                            text: 'N/A'
                            font_size: '14sp'
                        ValueLabel:
                            id: weight_change_3m
                            text: 'N/A'
                            font_size: '14sp'
                        ValueLabel:
                            id: weight_change_6m
                            text: 'N/A'
                            font_size: '14sp'

                        # Reps Row
                        Label:
                            text: 'Reps Δ:'
                            halign:'right'
                            padding_x: dp(5)
                            size_hint_x: 0.25
                            font_size: '14sp'
                        ValueLabel:
                            id: reps_change_1m
                            text: 'N/A'
                            font_size: '14sp'
                        ValueLabel:
                            id: reps_change_3m
                            text: 'N/A'
                            font_size: '14sp'
                        ValueLabel:
                            id: reps_change_6m
                            text: 'N/A'
                            font_size: '14sp'

                        # Sets Row
                        Label:
                            text: 'Sets Δ:'
                            halign:'right'
                            padding_x: dp(5)
                            size_hint_x: 0.25
                            font_size: '14sp'
                        ValueLabel:
                            id: sets_change_1m
                            text: 'N/A'
                            font_size: '14sp'
                        ValueLabel:
                            id: sets_change_3m
                            text: 'N/A'
                            font_size: '14sp'
                        ValueLabel:
                            id: sets_change_6m
                            text: 'N/A'
                            font_size: '14sp'

        Screen:
            name: 'add_exercise'
            ScrollView:
                do_scroll_x: False
                bar_width: dp(10)
                
                BoxLayout:
                    orientation: 'vertical'
                    padding: dp(20)
                    spacing: dp(15)
                    size_hint_y: None
                    height: self.minimum_height

                    HeaderLabel:
                        text: 'Add New Exercise'

                    GridLayout:
                        cols: 2
                        spacing: dp(10)
                        size_hint_y: None
                        height: dp(60)

                        InputLabel:
                            text: 'Exercise Name:'
                        TextInput:
                            id: exercise_name_input
                            multiline: False
                            hint_text: 'e.g., Bench Press'
                            write_tab: False
                            font_size: '16sp'
                            padding: dp(10), dp(10)

                    NavButton:
                        text: 'Save Exercise'
                        on_press: root.save_new_exercise()
                    NavButton:
                        text: 'Back to Log'
                        on_press: root.screen_manager.current = 'main'

        Screen:
            name: 'add_routine'
            ScrollView:
                do_scroll_x: False
                bar_width: dp(10)
                
                BoxLayout:
                    orientation: 'vertical'
                    padding: dp(20)
                    spacing: dp(15)
                    size_hint_y: None
                    height: self.minimum_height

                    HeaderLabel:
                        text: 'Add New Routine'

                    GridLayout:
                        cols: 2
                        spacing: dp(10)
                        size_hint_y: None
                        height: dp(60)

                        InputLabel:
                            text: 'Routine Name:'
                        TextInput:
                            id: routine_name_input
                            multiline: False
                            hint_text: 'e.g., Push Day'
                            write_tab: False
                            font_size: '16sp'
                            padding: dp(10), dp(10)

                    Widget:
                        size_hint_y: None
                        height: dp(10)

                    NavButton:
                        text: 'Save Routine'
                        on_press: root.save_new_routine()
                    NavButton:
                        text: 'Back to Log'
                        on_press: root.screen_manager.current = 'main'

        Screen:
            name: 'associate_exercise_with_routine'
            ScrollView:
                do_scroll_x: False
                bar_width: dp(10)
                
                BoxLayout:
                    orientation: 'vertical'
                    padding: dp(20)
                    spacing: dp(15)
                    size_hint_y: None
                    height: self.minimum_height

                    HeaderLabel:
                        text: 'Define Routine Content'

                    GridLayout:
                        cols: 2
                        spacing: dp(10)
                        size_hint_y: None
                        height: dp(60)

                        InputLabel:
                            text: 'Exercise:'
                        Spinner:
                            id: exercise_spinner_associate
                            text: "Select Exercise"
                            values: []
                            font_size: '16sp'
                            option_cls: "SpinnerOption"

                    GridLayout:
                        cols: 2
                        spacing: dp(10)
                        size_hint_y: None
                        height: dp(60)

                        InputLabel:
                            text: 'Add to Routine:'
                        Spinner:
                            id: routine_spinner_associate
                            text: "Select Routine"
                            values: []
                            font_size: '16sp'
                            option_cls: "SpinnerOption"

                    Label:
                        text: "(This links an exercise type to a routine type)"
                        size_hint_y: None
                        height: dp(30)
                        font_style: 'italic'
                        italic: True

                    Widget:
                        size_hint_y: None
                        height: dp(10)

                    NavButton:
                        text: 'Associate Exercise with Routine'
                        on_press: root.associate_exercise_with_routine()
                    NavButton:
                        text: 'Back to Log'
                        on_press: root.screen_manager.current = 'main'

        Screen:
            name: 'view_routine_exercises'
            BoxLayout:
                orientation: 'vertical'
                padding: dp(20)
                spacing: dp(15)

                HeaderLabel:
                    text: 'View Routine Exercises'
                    size_hint_y: None
                    height: self.texture_size[1] + dp(10)

                GridLayout:
                    cols: 2
                    spacing: dp(10)
                    size_hint_y: None
                    height: dp(60)

                    InputLabel:
                        text: 'Select Routine:'
                    Spinner:
                        id: routine_spinner_view
                        text: "Select Routine"
                        values: []
                        on_text: root.update_routine_exercises_display()
                        font_size: '16sp'
                        option_cls: "SpinnerOption"

                # ScrollView for the list of exercises
                ScrollView:
                    do_scroll_x: False
                    bar_width: dp(10)
                    size_hint_y: 1

                    Label:
                        id: routine_exercises_display
                        text: 'Select a routine above to see its exercises.'
                        size_hint_y: None
                        height: self.texture_size[1]
                        text_size: self.width, None
                        halign: 'left'
                        valign: 'top'
                        padding: dp(10), dp(10)
                        font_size: '16sp'

                NavButton:
                    text: 'Back to Log'
                    size_hint_y: None
                    height: dp(50)
                    on_press: root.screen_manager.current = 'main'

    # Status Label and Navigation Bar at the bottom (FIXED: removed duplicate)
    BoxLayout:
        orientation: 'vertical'
        size_hint: 1, 0.1
        spacing: dp(5)

        StatusLabel:
            id: status_label
            text: 'Ready'
            color: 0, 0.7, 0, 1
            font_size: '16sp'

        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: dp(50)
            spacing: dp(5)

            NavButton:
                text: 'Add Exercise'
                on_press: root.screen_manager.current = 'add_exercise'
            NavButton:
                text: 'Add Routine'
                on_press: root.screen_manager.current = 'add_routine'
            NavButton:
                text: 'Define'
                on_press: root.screen_manager.current = 'associate_exercise_with_routine'
            NavButton:
                text: 'View'
                on_press: root.screen_manager.current = 'view_routine_exercises'

''')



# --- App Class ---

class WeightTrackerApp(App):
    def build(self):
        try:
            logging.info("Building the WeightTracker UI...")
            # Set app title
            self.title = "Gym Tracker"
            return WeightTracker()
        except Exception as e:
            logging.critical(f"Critical error building the app: {e}", exc_info=True)
            # Optionally, show a simple error message UI if build fails
            return Label(text=f"Fatal Error:\n{e}\nSee logs for details.")

if __name__ == '__main__':
    WeightTrackerApp().run()