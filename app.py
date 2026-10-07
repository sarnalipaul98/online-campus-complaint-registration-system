from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3
import mysql.connector
from datetime import datetime, timedelta
import os
import calendar

app = Flask(__name__)
app.secret_key = "secretkey"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

COMMON_PASSWORD = "abc123"
ALLOWED_STUDENTS = [f"student{i}" for i in range(1, 851)]

# Make sessions permanent for 7 days
app.permanent_session_lifetime = timedelta(days=7)

# ---------------- DATABASE CONNECTION ----------------
def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "campus_complaints"),
        ssl_disabled=False
    )

# ---------------- INDEX ----------------
@app.route("/")
def index():
    return render_template("index.html")

# ---------------- THEME TOGGLE ----------------
@app.route("/toggle_theme")
def toggle_theme():
    current = session.get("theme", "light")
    session["theme"] = "dark" if current == "light" else "light"
    return redirect(request.referrer or "/")

# ---------------- STUDENT LOGIN ----------------
@app.route("/student", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username not in ALLOWED_STUDENTS:
            flash("Invalid Student ID", "danger")
            return render_template("student_login.html")

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT password FROM student_passwords WHERE student_id=%s", (username,))
        row = cursor.fetchone()
        db.close()

        real_password = row[0] if row else COMMON_PASSWORD

        if password == real_password:
            session["role"] = "student"
            session["username"] = username
            session.setdefault("theme", "light")
            
            return redirect("/student_home")
        else:
            flash("Invalid password", "danger")

    return render_template("student_login.html")
#------------------Student Home-----------------------
@app.route("/student_home")
def student_home():
    if "role" not in session or session["role"] != "student":
        return redirect("/student")

    student_id = session.get("username")
    student_name = session.get("student_name")
    overall_satisfaction = 0

    db = get_db()  # Use MySQL connection
    cursor = db.cursor()

    # Total complaints
    cursor.execute("SELECT COUNT(*) FROM complaints WHERE student_id=%s", (student_id,))
    total = cursor.fetchone()[0]

    # Resolved complaints
    cursor.execute("SELECT COUNT(*) FROM complaints WHERE student_id=%s AND status='Resolved'", (student_id,))
    resolved = cursor.fetchone()[0]

    if total > 0:
        overall_satisfaction = round((resolved / total) * 10, 2)
    else:
        overall_satisfaction = 0

    db.close()

    return render_template(
        "student_home.html",
        student_id=student_id,
        student_name=student_name,
        overall_satisfaction=overall_satisfaction
    )


#--------------------Tracking------------------------
import matplotlib.pyplot as plt
import os

@app.route("/track/<int:complaint_id>")
def track_complaint(complaint_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT student_name, student_id, progress_percent FROM complaints WHERE id=%s",
        (complaint_id,)
    )
    complaint = cursor.fetchone()
    db.close()

    student_name = complaint[0]
    student_id = complaint[1]
    progress_percent = complaint[2]

    print("DB value:", progress_percent)   # ✅ DEBUG

    # Steps and values
    steps = ["Complaint Submitted","Received By Manager","Verified By Manager","Work In Progress","Finalizing Work","Solved Succesfully"]
    progress = [0,20,40,60,80,100]

    # ✅ SAFE CHECK (IMPORTANT)
    if progress_percent not in progress:
        progress_percent = 0

    index = progress.index(progress_percent)

    # X and Y
    x = steps[:index+1]
    y = progress[:index+1]

    plt.figure(figsize=(12,8))
    plt.plot(x, y, marker='o', linewidth=2)
    plt.scatter(x[-1], y[-1], s=100)

    plt.ylim(0, 100)
    plt.yticks([0,20,40,60,80,100])
    
    plt.yticks([0, 20, 40, 60, 80, 100], fontsize=14)  # Y-axis labels
    
    plt.xlabel("Steps", fontsize=16)                   # X-axis title
    plt.ylabel("Completion (%)", fontsize=16)          # Y-axis title
    plt.title("Complaint Tracking", fontsize=18)       # Chart title
    
    
    plt.title("Complaint Tracking", fontsize=18)       # Chart title
    

    plt.xlabel("Steps Of Work ")
    plt.ylabel("Completion (%) Of Work")
    plt.title("Complaint Tracking")
    plt.grid(True)

    # Save image
    if not os.path.exists("static"):
        os.makedirs("static")

    image_path = f"static/track_{complaint_id}.png"
    plt.savefig(image_path)
    plt.close()

    return render_template("track.html",
                           student_name=student_name,
                           student_id=student_id,
                           image=image_path)


#------------------Manager tracking update--------------
@app.route("/update_progress", methods=["POST"])
def update_progress():
    complaint_id = request.form["complaint_id"]
    progress = int(request.form["progress"])

    # 👇 map value to text
    progress_map = {
        0: 'Complaint Submitted',
        20: 'Received by Admin',
        40: 'Verification Done',
        60: 'Work in Progress',
        80: 'Almost Completed',
        100: 'Solved Succesfully'
    }

    progress_text = progress_map.get(progress, "Submitted")

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "UPDATE complaints SET progress_percent=%s, progress_text=%s WHERE id=%s",
        (progress, progress_text, complaint_id)
    )

    db.commit()
    db.close()

    flash("Progress updated successfully!", "success")

    return redirect(url_for("manager_dashboard"))

# ---------------- ADMIN LOGIN ----------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s AND role='admin'", (username, password))
        user = cursor.fetchone()
        db.close()

        if user:
            session["role"] = "admin"
            session["username"] = username
            session.setdefault("theme", "light")
            session.permanent = True
            return redirect("/admin_home")
        else:
            flash("Invalid admin credentials", "danger")

    return render_template("admin_login.html")


#--------------------ADMIN HOME----------------------------
@app.route("/admin_home")
def admin_home():
    # Protect page: only admin can access
    if "role" not in session or session["role"] != "admin":
        return redirect("/admin")

    db = get_db()
    cursor = db.cursor()

    # ---------- Department-wise counts for pie chart ----------
    cursor.execute("SELECT department, COUNT(*) FROM complaints GROUP BY department")
    dept_data = cursor.fetchall()
    departments = [d[0] for d in dept_data]
    dept_counts = [d[1] for d in dept_data]

    # ---------- Plot Pie Chart ----------
    plt.figure(figsize=(6,6))
    plt.pie(
        dept_counts,
        labels=departments,
        autopct='%1.1f%%',
        startangle=140,
        colors=['#FF6384','#36A2EB','#FFCE56','#4BC0C0','#9966FF','#FF9F40','#8AC926']
    )
    plt.title("Department-wise Complaints")
    plt.tight_layout()

    pie_chart_path = "static/department_pie_chart.png"
    if not os.path.exists("static"):
        os.makedirs("static")
    plt.savefig(pie_chart_path)
    plt.close()

    # ---------- Today & Yesterday ----------
    today = datetime.today().date()
    yesterday = today - timedelta(days=1)

    cursor.execute("""
        SELECT COUNT(*) FROM complaints
        WHERE DATE(applied_time) = %s OR DATE(applied_time) = %s
    """, (today, yesterday))
    new_count = cursor.fetchone()[0]

    # Latest complaint
    cursor.execute("""
        SELECT id, student_name
        FROM complaints
        WHERE DATE(applied_time) = %s OR DATE(applied_time) = %s
        ORDER BY applied_time DESC
        LIMIT 1
    """, (today, yesterday))
    latest_complaint = cursor.fetchone()
    latest_complaint_id = latest_complaint[0] if latest_complaint else "-"
    latest_student = latest_complaint[1] if latest_complaint else "-"

    # Total, Pending, Resolved
    cursor.execute("SELECT COUNT(*) FROM complaints")
    total_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='Pending'")
    pending_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'")
    resolved_complaints = cursor.fetchone()[0]

    # Overall Satisfaction (scale 10)
    satisfaction = round((resolved_complaints / total_complaints) * 10, 1) if total_complaints else 0

    # ---------- Month-wise Bar Graph ----------
cursor.execute("""
    SELECT 
        YEAR(applied_time) AS year,
        MONTH(applied_time) AS month,
        COUNT(*) AS total
    FROM complaints
    GROUP BY YEAR(applied_time), MONTH(applied_time)
    ORDER BY YEAR(applied_time), MONTH(applied_time)
""")
month_data = cursor.fetchall()
    

    months = list(calendar.month_name)[1:]
    counts_dict = {month: 0 for month in months}
    for row in month_data:
        dt = row[0] if isinstance(row[0], datetime) else datetime.strptime(str(row[0]), "%Y-%m-%d %H:%M:%S")
        month_name = dt.strftime("%B")
        counts_dict[month_name] = row[1]
    counts = [counts_dict[m] for m in months]

    # Bar Graph
    plt.figure(figsize=(10,5))
    plt.bar(months, counts, color='skyblue')
    plt.title("Complaints Month-wise")
    plt.xlabel("Month")
    plt.ylabel("Number of Complaints")
    plt.xticks(rotation=45)
    plt.tight_layout()

    bar_graph_path = "static/complaints_bar_graph.png"
    if not os.path.exists("static"):
        os.makedirs("static")
    plt.savefig(bar_graph_path)
    plt.close()

    # ---------- DEPARTMENT COUNTS ----------
    cursor.execute("SELECT department, COUNT(*) FROM complaints GROUP BY department")
    rows = cursor.fetchall()

    db.close()

    # List all possible departments (replace with your actual department names) 
    all_departments = [
    "Computer Science / Information Technology",
    "Mechanical Engineering",
    "Civil Engineering",
    "Electrical & Electronics Engineering",
    "Electronics & Communication Engineering",
    "Management Studies (BBA / MBA)",
    "Commerce (B.Com / M.Com)",
    "Science Department",
    "Arts & Humanities",
    "Law Department"
]  

    # Create counts list (0 if department has no complaints)
    counts_dict = dict(rows)
    counts = [counts_dict.get(dep, 0) for dep in all_departments]

    # Optional: same colors as your dashboard
    colors = ['#FF6384','#36A2EB','#FFCE56','#4BC0C0','#9966FF','#FF9F40','#8AC926']
    
    # ---------- Render Template ----------
    return render_template(
        "admin_home.html",
        new_count=new_count,
        latest_complaint_id=latest_complaint_id,
        latest_student=latest_student,
        satisfaction=satisfaction,
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        resolved_complaints=resolved_complaints,
        bar_graph_url=bar_graph_path,
        pie_chart_url=pie_chart_path,
        departments=all_departments,
        counts=counts,
        theme=session.get("theme", "light")
    )



# ---------------- MANAGER LOGIN ----------------
@app.route("/manager", methods=["GET", "POST"])
def manager_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s AND role='manager'",
            (username, password)
        )
        user = cursor.fetchone()
        db.close()

        if user:
            session["role"] = "manager"
            session["username"] = username
            session.setdefault("theme", "light")
            session.permanent = True
            return redirect("/manager_home")
        else:
            flash("Invalid manager credentials", "danger")

    return render_template("manager_login.html")


#-------------------------MANAGER HOME-------------------
#--------------------MANAGER HOME----------------------------
@app.route("/manager_home")
def manager_home():

    # ✅ Protect page: only manager can access
    if "role" not in session or session["role"] != "manager":
        return redirect("/manager")

    db = get_db()
    cursor = db.cursor()

    # ---------- Today & Yesterday ----------
    today = datetime.today().date()
    yesterday = today - timedelta(days=1)

    cursor.execute("""
        SELECT COUNT(*) FROM complaints
        WHERE DATE(applied_time) = %s OR DATE(applied_time) = %s
    """, (today, yesterday))
    new_count = cursor.fetchone()[0]

    # ---------- Latest Complaint ----------
    cursor.execute("""
        SELECT id, student_name
        FROM complaints
        WHERE DATE(applied_time) = %s OR DATE(applied_time) = %s
        ORDER BY applied_time DESC
        LIMIT 1
    """, (today, yesterday))

    latest_complaint = cursor.fetchone()
    latest_complaint_id = latest_complaint[0] if latest_complaint else "-"
    latest_student = latest_complaint[1] if latest_complaint else "-"

    # ---------- Total, Pending, Resolved ----------
    cursor.execute("SELECT COUNT(*) FROM complaints")
    total_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='Pending'")
    pending_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'")
    resolved_complaints = cursor.fetchone()[0]

    # ---------- Satisfaction ----------
    satisfaction = round((resolved_complaints / total_complaints) * 10, 1) if total_complaints else 0

    db.close()

    # ---------- Render Template ----------
    return render_template(
        "manager_home.html",
        new_count=new_count,
        latest_complaint_id=latest_complaint_id,
        latest_student=latest_student,
        satisfaction=satisfaction,
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        resolved_complaints=resolved_complaints,
        theme=session.get("theme", "light")
    )

# ---------------- MANAGER RESOLVE WITH PROOF ----------------
@app.route("/manager_resolve/<int:id>", methods=["GET","POST"])
def manager_resolve(id):
    if "role" not in session or session["role"] != "manager":
        return redirect("/manager")

    file = request.files.get("proof_image")
    filename = None

    if file and file.filename != "":
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)

        
        if not os.path.exists(app.config["UPLOAD_FOLDER"]):
            os.makedirs(app.config["UPLOAD_FOLDER"])

        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    resolved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE complaints 
        SET status='Resolved',
            resolved_time=%s,
            proof_image=%s
        WHERE id=%s
    """, (resolved_time, filename, id))

    db.commit()
    db.close()

    flash("Complaint resolved successfully!", "success")
    return redirect("/manager_dashboard")


@app.route("/delete_proof/<int:id>")
def delete_proof(id):
    if "role" not in session or session["role"] != "manager":
        return redirect("/manager")

    db = get_db()
    cursor = db.cursor()

    # Get filename
    cursor.execute("SELECT proof_image FROM complaints WHERE id=%s", (id,))
    result = cursor.fetchone()

    if result and result[0]:
        filename = result[0]
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        # Delete file from folder
        if os.path.exists(filepath):
            os.remove(filepath)

        # Remove filename from DB
        cursor.execute("UPDATE complaints SET proof_image=NULL WHERE id=%s", (id,))
        db.commit()

    db.close()

    flash("Proof image deleted successfully", "success")
    return redirect("/manager_dashboard")



# ---------------- STUDENT DASHBOARD ----------------
@app.route("/student_dashboard", methods=["GET", "POST"])
def student_dashboard():
    if "role" not in session or session["role"] != "student":
        return redirect("/student")

    student_id = session["username"]
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        name = f"{first_name} {last_name}"  # combine them into a single string
        sid = request.form["sid"]
        phone = request.form["phone"]
        # Check if phone is 10 digits
        if not phone.isdigit() or len(phone) != 10:
            flash("Phone number must be exactly 10 digits", "danger")
            return redirect("/student_dashboard")
        
        year = request.form["year"]
        student_type = request.form["student_type"]

        status = "pending"
        
        department = request.form["department"]
        category = request.form["category"]
        description = request.form["description"]
        file = request.files["file"]
        filename = ""

        if sid != student_id:
            flash(f"Student ID must be {student_id}", "danger")
            return redirect("/student_dashboard")

        if file and file.filename != "":
            filename = file.filename
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        applied_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
INSERT INTO complaints
(student_name, student_id, department, category, description, file, status, applied_time, phone, year, student_type)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
""",(name, sid, department, category, description, filename, status, applied_time, phone, year, student_type))
        db.commit()
        flash("Complaint submitted successfully", "success")
        db.close()
        return redirect("/student_dashboard")

    # Filter complaints
    status_filter = request.args.get("status", "All")
    query = "SELECT * FROM complaints WHERE student_id=%s"
    params = [student_id]
    if status_filter in ["Pending", "Resolved"]:
        query += " AND status=%s"
        params.append(status_filter)
    query += " ORDER BY applied_time DESC"
    cursor.execute(query, tuple(params))
    complaints = cursor.fetchall()
    db.close()

    return render_template("student_dashboard.html", complaints=complaints, student_id=student_id,
                           theme=session.get("theme", "light"), status_filter=status_filter)

#-----------------Student All---------------------

# -----------------Student All---------------------
@app.route("/student_all")
def student_all():
    if "role" not in session or session["role"] != "student":
        return redirect("/student")

    student_id = session["username"]

    db = get_db()
    cursor = db.cursor()

    # Explicitly select all columns including rating as last
    cursor.execute("""
        SELECT id, student_name, student_id, department, category, description, file,
               status, applied_time, resolved_time, admin_message, proof_image, phone,
               year, student_type, manager_message, rating
        FROM complaints
        WHERE student_id=%s
        ORDER BY applied_time DESC
    """, (student_id,))

    complaints = cursor.fetchall()
    db.close()

    return render_template(
        "student_all.html",
        complaints=complaints,
        student_id=student_id,
        theme=session.get("theme", "light")
    )

#-----------------Student Pending------------------
@app.route("/student_pending")
def student_pending():

    if "role" not in session or session["role"] != "student":
        return redirect("/student")

    student_id = session["username"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT * FROM complaints WHERE student_id=%s AND status='Pending' ORDER BY applied_time DESC",
        (student_id,)
    )

    complaints = cursor.fetchall()
    db.close()

    return render_template(
        "student_pending.html",
        complaints=complaints,
        student_id=student_id,
        theme=session.get("theme", "light")
    )

#------------------Student Resolved---------------
@app.route("/student_resolved")
def student_resolved():

    if "role" not in session or session["role"] != "student":
        return redirect("/student")

    student_id = session["username"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
    SELECT id, student_name, student_id, department, category, description, file,
           status, applied_time, resolved_time, admin_message, proof_image, phone, year,
           student_type, manager_message
    FROM complaints
    WHERE student_id=%s AND status='Resolved'
    ORDER BY applied_time DESC
""", (student_id,))

    complaints = cursor.fetchall()
    db.close()

    return render_template(
        "student_resolved.html",
        complaints=complaints,
        student_id=student_id,
        theme=session.get("theme", "light")
    )

#--------------------Tracking List---------------
@app.route("/track_list")
def track_list():
    if "role" not in session or session["role"] != "student":
        return redirect("/student")

    student_id = session["username"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT * FROM complaints
        WHERE student_id=%s
        ORDER BY applied_time DESC
    """, (student_id,))

    complaints = cursor.fetchall()
    db.close()

    return render_template(
        "track_list.html",
        complaints=complaints,
        theme=session.get("theme", "light")
    )


#--------------------Student Message-------------
@app.route("/student_messages")
def student_messages():
    if "role" not in session or session["role"] != "student":
        return redirect("/student")

    student_id = session["username"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT * FROM complaints
        WHERE student_id=%s
        ORDER BY applied_time DESC
    """, (student_id,))

    complaints = cursor.fetchall()
    db.close()

    return render_template(
        "student_messages.html",
        complaints=complaints,
        theme=session.get("theme", "light")
    )


#--------------Rating------------------------
@app.route("/rating")
def rating_page():
    if "role" not in session or session["role"] != "student":
        return redirect("/student")

    student_id = session["username"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT * FROM complaints
        WHERE student_id=%s
        ORDER BY applied_time DESC
    """, (student_id,))

    complaints = cursor.fetchall()
    db.close()

    return render_template(
        "rating.html",
        complaints=complaints,
        theme=session.get("theme", "light")
    )
#------------------SUBMIT RATING-----------------
#------------------SUBMIT RATING-----------------
@app.route('/submit_rating/<int:id>', methods=['POST'])
def submit_rating(id):
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('student_login'))

    rating = request.form['rating']

    db = get_db()
    cursor = db.cursor()

    # Check if rating is already set
    cursor.execute("SELECT rating FROM complaints WHERE id=%s", (id,))
    existing = cursor.fetchone()

    if existing and existing[0] is None:
        cursor.execute("UPDATE complaints SET rating=%s WHERE id=%s", (rating, id))
        db.commit()
        flash("Rating submitted successfully!", "success")
    else:
        flash("You have already submitted a rating for this complaint.", "danger")

    db.close()
    return redirect(url_for('student_all'))

#----------------STUDENT CHAT---------------------
@app.route("/student_chat/<int:complaint_id>", methods=["GET", "POST"])
def student_chat(complaint_id):
    if "role" not in session or session["role"] != "student":
        return redirect(url_for("student_login"))

    db = get_db()
    cursor = db.cursor()

    # Send message
    if request.method == "POST":
        message = request.form["message"]
        cursor.execute("""
            INSERT INTO messages (complaint_id, sender, message)
            VALUES (%s, %s, %s)
        """, (complaint_id, session["username"], message))
        db.commit()

    # Get messages
    cursor.execute("""
        SELECT sender, message, timestamp
        FROM messages
        WHERE complaint_id = %s
        ORDER BY timestamp ASC
    """, (complaint_id,))
    raw_chats = cursor.fetchall()
    db.close()

    # Transform messages to display "you:" for student
    chats = []
    for sender, message, timestamp in raw_chats:
        display_sender = "you" if sender == session["username"] else sender
        chats.append({
            "sender": display_sender,
            "message": message,
            "timestamp": timestamp
        })

    return render_template(
        "student_chat.html",
        chats=chats,
        complaint_id=complaint_id
    )
# ---------------- ADMIN DASHBOARD ----------------
# ---------------- ADMIN DASHBOARD ----------------
from datetime import date, timedelta

@app.route("/admin_dashboard")
def admin_dashboard():
    # Only admin can access
    if "role" not in session or session["role"] != "admin":
        return redirect("/admin")

    # Get filters from query parameters
    search = request.args.get("search", "").strip()
    sort_column = request.args.get("sort", "applied_time")
    order = request.args.get("order", "DESC")
    status_filter = request.args.get("status", "All")  # 'Pending', 'Resolved', 'New', or 'All'

    # Only allow sorting by these columns
    allowed_columns = {
        "id": "id",
        "student_id": "student_id",
        "status": "status",
        "applied_time": "applied_time"
    }
    sort_column = allowed_columns.get(sort_column, "applied_time")
    order = "ASC" if order.upper() == "ASC" else "DESC"

    # Dates for New complaints
    today = date.today().strftime("%Y-%m-%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    db = get_db()
    cursor = db.cursor()

    # ---------------- Fetch complaints ----------------
    query = """
        SELECT id, student_name, student_id, department, category, description, file,
               status, applied_time, resolved_time, admin_message, proof_image,
               phone, year, student_type, manager_message, rating,
               progress_text, progress_percent
        FROM complaints
        WHERE 1=1
    """
    params = []

    # ---------------- Apply status filter ----------------
    if status_filter in ["Pending", "Resolved"]:
        query += " AND status=%s"
        params.append(status_filter)
    elif status_filter == "New":
        query += " AND DATE(applied_time) IN (%s, %s)"
        params.extend([today, yesterday])
    elif status_filter == "Overdue":
        one_week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        query += " AND status='Pending' AND applied_time <= %s"
        params.append(one_week_ago)
    elif status_filter == "Priority":
    # Select complaints in specific categories AND not resolved
        query += " AND status='Pending' AND category IN (%s, %s, %s, %s)"
        params.extend(["Security", "Electricity", "Academic Issue", "Ragging"])
    # else: status_filter == 'All', do nothing

    # ---------------- Apply search filter ----------------
    if search:
        query += " AND (student_id LIKE %s OR id LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    # Apply sorting
    query += f" ORDER BY {sort_column} {order}"

    cursor.execute(query, tuple(params))
    complaints = cursor.fetchall()

    # ---------------- Department-wise counts for chart ----------------
    cursor.execute("SELECT department, COUNT(*) FROM complaints GROUP BY department")
    dept_data = cursor.fetchall()
    departments = [d[0] for d in dept_data]
    counts = [d[1] for d in dept_data]

    # ---------------- Summary counts ----------------
    cursor.execute("SELECT COUNT(*) FROM complaints")
    total_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'")
    total_resolved = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status='Pending'")
    total_pending = cursor.fetchone()[0]


    db.close()

    # Render the admin dashboard template
    return render_template(
        "admin_dashboard.html",
        complaints=complaints,
        theme=session.get("theme", "light"),
        status_filter=status_filter,
        departments=departments,
        counts=counts,
        total_complaints=total_complaints,
        total_resolved=total_resolved,
        total_pending=total_pending
        
    )
# ---------------- MANAGER DASHBOARD ----------------
from flask import request
from datetime import date, timedelta
@app.route("/manager_dashboard")
def manager_dashboard():
    if "role" not in session or session["role"] != "manager":
        return redirect("/manager")

    search = request.args.get("search", "").strip()
    sort_column = request.args.get("sort", "applied_time")
    order = request.args.get("order", "DESC")
    status_filter = request.args.get("status", "All")


    today = date.today().strftime("%Y-%m-%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    allowed_columns = {
        "id": "id",
        "student_id": "student_id",
        "status": "status",
        "applied_time": "applied_time"
    }

    sort_column = allowed_columns.get(sort_column, "applied_time")
    order = "ASC" if order == "ASC" else "DESC"

    db = get_db()
    cursor = db.cursor()

    query = """
SELECT id, student_name, student_id, department, category, description,
file, status, applied_time, resolved_time,
admin_message, proof_image, phone, year, student_type,
manager_message, progress_percent
FROM complaints
WHERE 1=1
"""
    params = []

    if "department" in session:
        query += " AND department=%s"
        params.append(session["department"])

    if status_filter in ["Pending", "Resolved"]:
        query += " AND status=%s"
        params.append(status_filter)

    elif status_filter == "New":
        query += " AND DATE(applied_time) IN (%s, %s)"
        params.extend([today, yesterday])

    elif status_filter == "Overdue":
        one_week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        query += " AND status='Pending' AND applied_time <= %s"
        params.append(one_week_ago)

    elif status_filter == "Priority":
        query += " AND status='Pending' AND category IN (%s, %s, %s, %s)"
        params.extend(["Security", "Electricity", "Academic Issue", "Ragging"])    

    if search:
        query += " AND (student_id LIKE %s OR id LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += f" ORDER BY {sort_column} {order}"

    cursor.execute(query, tuple(params))
    complaints = cursor.fetchall()

    # ✅ ADD THIS
    for c in complaints:
        print(c)
    
    db.close()

    return render_template(
        "manager_dashboard.html",
        complaints=complaints,
        theme=session.get("theme", "light"),
        status_filter=status_filter
    )


#------------------MANAGER CHAT---------------------
@app.route("/manager_chat/<int:complaint_id>", methods=["GET","POST"])
def manager_chat(complaint_id):

    if "role" not in session or session["role"] != "manager":
        return redirect(url_for("manager_login"))

    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        message = request.form["message"]
        cursor.execute("""
            INSERT INTO messages (complaint_id, sender, message)
            VALUES (%s, %s, %s)
        """, (complaint_id, session["username"], message))
        db.commit()

    # GET messages
    cursor.execute("""
        SELECT sender, message, timestamp
        FROM messages
        WHERE complaint_id=%s
        ORDER BY timestamp ASC
    """, (complaint_id,))

    chats_raw = cursor.fetchall()
    chats = []

    for sender, message, timestamp in chats_raw:
        
        display_sender = "you" if sender == session["username"] else sender
        chats.append({
            "sender": display_sender,
            "message": message,
            "timestamp": timestamp
        })

    db.close()

    return render_template(
        "manager_chat.html",
        chats=chats,
        complaint_id=complaint_id
    )



#------------------MANAGER TO ADMIN CHAT---------------------
@app.route("/manager_admin_chat/<int:complaint_id>", methods=["GET","POST"])
def manager_admin_chat(complaint_id):

    if "role" not in session or session["role"] != "manager":
        return redirect(url_for("manager_login"))

    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        message = request.form["message"]

        cursor.execute("""
            INSERT INTO admin_messages (complaint_id, sender, message)
            VALUES (%s, %s, %s)
        """, (complaint_id, session["username"], message))

        db.commit()

    cursor.execute("""
        SELECT sender, message, timestamp
        FROM admin_messages
        WHERE complaint_id=%s
        ORDER BY timestamp ASC
    """, (complaint_id,))

    chats_raw = cursor.fetchall()
    chats = []

    for sender, message, timestamp in chats_raw:
        display_sender = "you" if sender == session["username"] else sender

        chats.append({
            "sender": display_sender,
            "message": message,
            "timestamp": timestamp
        })

    db.close()

    return render_template(
        "manager_admin_chat.html",
        chats=chats,
        complaint_id=complaint_id
    )
# ---------------- RESOLVE COMPLAINT ----------------
@app.route("/resolve/<int:id>")
def resolve(id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/admin")

    db = get_db()
    cursor = db.cursor()
    resolved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE complaints SET status='Resolved', resolved_time=%s WHERE id=%s", (resolved_time, id))
    db.commit()
    db.close()
    return redirect("/admin_dashboard")

#-----------------submit----------------------
@app.route("/admin_message/<int:id>", methods=["POST"])
def admin_message(id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/admin")

    message = request.form.get("admin_message", "").strip()
    if not message:
        flash("Message cannot be empty", "danger")
        return redirect("/admin_dashboard")

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE complaints SET admin_message=%s WHERE id=%s",
        (message, id)
    )
    db.commit()
    db.close()
    flash("Message submitted successfully", "success")
    return redirect("/admin_dashboard")

#-------------------------edit----------------------
@app.route("/edit_admin_message/<int:id>")
def edit_admin_message(id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/admin")

    edit_id = id
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM complaints ORDER BY applied_time DESC")
    complaints = cursor.fetchall()
    db.close()

    return render_template("admin_dashboard.html",
                           complaints=complaints,
                           theme=session.get("theme", "light"),
                           status_filter=request.args.get("status","All"),
                           sort_column=request.args.get("sort","applied_time"),
                           sort_order=request.args.get("order","DESC"),
                           edit_id=edit_id)


#-------------------------------delete-----------------------------
@app.route("/delete_admin_message/<int:id>")
def delete_admin_message(id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/admin")

    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE complaints SET admin_message=NULL WHERE id=%s", (id,))
    db.commit()
    db.close()
    flash("Admin message deleted successfully", "success")
    return redirect("/admin_dashboard")



#------------------------- MANAGER EDIT ----------------------
@app.route("/edit_manager_message/<int:id>")
def edit_manager_message(id):
    if "role" not in session or session["role"] != "manager":
        return redirect("/manager")

    edit_id = id
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM complaints ORDER BY applied_time DESC")
    complaints = cursor.fetchall()
    db.close()

    return render_template("manager_dashboard.html",
                           complaints=complaints,
                           theme=session.get("theme", "light"),
                           status_filter=request.args.get("status","All"),
                           sort_column=request.args.get("sort","applied_time"),
                           sort_order=request.args.get("order","DESC"),
                           edit_id=edit_id)

#------------------------------- MANAGER DELETE -----------------------------
@app.route("/delete_manager_message/<int:id>")
def delete_manager_message(id):
    if "role" not in session or session["role"] != "manager":
        return redirect("/manager")

    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE complaints SET manager_message=NULL WHERE id=%s", (id,))
    db.commit()
    db.close()
    flash("Manager message deleted successfully", "success")
    return redirect("/manager_dashboard")


@app.route("/manager_message/<int:id>", methods=["POST"])
def manager_message(id):
    if "role" not in session or session["role"] != "manager":
        return redirect("/manager")

    message = request.form.get("manager_message")

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "UPDATE complaints SET manager_message=%s WHERE id=%s",
        (message, id)
    )

    db.commit()
    db.close()

    flash("Manager message updated successfully", "success")
    return redirect("/manager_dashboard")




#------------------ADMIN CHAT---------------------
@app.route("/admin_chat/<int:complaint_id>", methods=["GET","POST"])
def admin_chat(complaint_id):

    if "role" not in session or session["role"] != "admin":
        return redirect(url_for("admin_login"))

    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        message = request.form["message"]

        cursor.execute("""
            INSERT INTO admin_messages (complaint_id, sender, message)
            VALUES (%s, %s, %s)
        """, (complaint_id, session["username"], message))

        db.commit()

    cursor.execute("""
        SELECT sender, message, timestamp
        FROM admin_messages
        WHERE complaint_id=%s
        ORDER BY timestamp ASC
    """, (complaint_id,))

    chats_raw = cursor.fetchall()
    chats = []

    for sender, message, timestamp in chats_raw:
        display_sender = "you" if sender == session["username"] else sender

        chats.append({
            "sender": display_sender,
            "message": message,
            "timestamp": timestamp
        })

    db.close()

    return render_template(
        "admin_chat.html",
        chats=chats,
        complaint_id=complaint_id
    )

# ---------------- CHANGE PASSWORD (dashboard only) ----------------
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "role" not in session:
        flash("Please login first", "danger")
        return redirect("/")

    role = session["role"]
    username = session["username"]

    # ✅ STEP 1: store next page ONLY when opening page
    if request.method == "GET":
        next_page = request.args.get("next")
        session["next_page"] = next_page if next_page else None

    # ✅ STEP 2: always get from session
    next_page = session.get("next_page")

    if request.method == "POST":
        old = request.form["old_password"]
        new = request.form["new_password"]

        db = get_db()
        cursor = db.cursor()

        if role == "student":
            cursor.execute("SELECT password FROM student_passwords WHERE student_id=%s", (username,))
            row = cursor.fetchone()
            current = row[0] if row else COMMON_PASSWORD

            if old != current:
                flash("Old password incorrect", "danger")
                db.close()
                return redirect("/change_password")

            cursor.execute("""
                INSERT INTO student_passwords (student_id,password)
                VALUES (%s,%s)
                ON DUPLICATE KEY UPDATE password=%s
            """, (username, new, new))

        else:
            cursor.execute("SELECT password FROM users WHERE username=%s AND role=%s", (username, role))
            row = cursor.fetchone()

            if not row or old != row[0]:
                flash("Old password incorrect", "danger")
                db.close()
                return redirect("/change_password")

            cursor.execute(
                "UPDATE users SET password=%s WHERE username=%s AND role=%s",
                (new, username, role)
            )

        db.commit()
        db.close()
        flash("Password updated successfully", "success")
        return redirect("/change_password")


        # fallback
        if role == "student":
            return redirect("/student_home")
        elif role == "manager":
            return redirect("/manager_dashboard")
        else:
            return redirect("/admin_dashboard")

    
    return render_template("change_password.html", next_page=next_page)

# ---------------- FORGOT PASSWORD (login page) ----------------
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    # Get user and role from query string
    user_id = request.args.get("user", "")
    role = request.args.get("role", "student")  # default to student if not passed

    if request.method == "POST":
        user_type = request.form.get("user_type")  # "student", "manager", "admin"
        username = request.form.get("username")
        new_password = request.form.get("new_password")

        db = get_db()
        cursor = db.cursor()

        if user_type == "student":
            if not username or username not in ALLOWED_STUDENTS:
                flash("Invalid Student ID", "danger")
                db.close()
                return redirect(url_for("forgot_password", user=username, role="student"))
            cursor.execute("""
                INSERT INTO student_passwords (student_id,password)
                VALUES (%s,%s)
                ON DUPLICATE KEY UPDATE password=%s
            """, (username, new_password, new_password))
            db.commit()
            db.close()
            flash("Password reset successful. Please login.", "success")
            return redirect("/student")

        elif user_type == "manager":
            if not username:
                flash("Invalid Manager Username", "danger")
                db.close()
                return redirect(url_for("forgot_password", user=username, role="manager"))
            cursor.execute(
                "UPDATE users SET password=%s WHERE username=%s AND role='manager'",
                (new_password, username)
            )
            db.commit()
            db.close()
            flash("Password reset successful. Please login.", "success")
            return redirect("/manager")

        elif user_type == "admin":
            if not username:
                flash("Invalid Admin Username", "danger")
                db.close()
                return redirect(url_for("forgot_password", user=username, role="admin"))
            cursor.execute(
                "UPDATE users SET password=%s WHERE username=%s AND role='admin'",
                (new_password, username)
            )
            db.commit()
            db.close()
            flash("Password reset successful. Please login.", "success")
            return redirect("/admin")

        else:
            db.close()
            flash("Invalid role", "danger")
            return redirect("/")

    return render_template("forgot_password.html", user_id=user_id, role=role)

#--------------------Admin feedback------------------
#--------------------Admin feedback------------------
@app.route("/admin_feedback")
def admin_feedback():
    # Only admins can access
    if "role" not in session or session["role"] != "admin":
        return redirect("/admin")

    # Get student_id from search form
    student_id = request.args.get("student_id", "").strip()  # remove spaces

    db = get_db()
    cursor = db.cursor()

    # Base query
    query = """
        SELECT id, student_name, student_id, department, category, rating
        FROM complaints
    """
    params = []

    # Filter if student_id is provided
    if student_id:
        query += " WHERE student_id = %s"  # MySQL placeholder
        params.append(student_id)

    query += " ORDER BY applied_time DESC"

    # Execute query with parameters
    cursor.execute(query, params)
    feedbacks = cursor.fetchall()
    db.close()

    return render_template(
        "admin_feedback.html",
        feedbacks=feedbacks,
        theme=session.get("theme", "light")
    )

#----------------------------MANAGER FEEDBACK-------------------------
@app.route("/manager_feedback")
def manager_feedback():
    if "role" not in session or session["role"] != "manager":
        return redirect("/manager")

    student_id = request.args.get("student_id", "").strip()

    db = get_db()
    cursor = db.cursor()

    query = """
        SELECT id, student_name, student_id, department, category, rating
        FROM complaints
        WHERE 1=1
    """
    params = []

    # OPTIONAL: show only manager department
    if "department" in session:
        query += " AND department=%s"
        params.append(session["department"])

    # search filter
    if student_id:
        query += " AND student_id = %s"
        params.append(student_id)

    cursor.execute(query, tuple(params))
    feedbacks = cursor.fetchall()

    db.close()

    return render_template("manager_feedback.html", feedbacks=feedbacks)

#---------------------Complaint Analysis--------------------
from flask import render_template, session, redirect
from datetime import datetime
import calendar
from collections import Counter
import matplotlib.pyplot as plt
import os

@app.route("/complaint_analysis")
def complaint_analysis():
    # Only admin can access
    if "role" not in session or session["role"] != "admin":
        return redirect("/admin")

    db = get_db()
    cursor = db.cursor()

    # Fetch all applied_time from complaints
    cursor.execute("SELECT applied_time FROM complaints ORDER BY applied_time ASC")
    data = cursor.fetchall()
    db.close()

    # Count complaints per month
    months_counter = Counter()
    for row in data:
        dt = row[0]
        if isinstance(dt, str):
            dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        month_name = dt.strftime("%B")
        months_counter[month_name] += 1

    # Always show all months in order
    month_order = [calendar.month_name[i] for i in range(1, 13)]
    months = month_order
    counts = [months_counter.get(m, 0) for m in months]  # 0 if no complaints

    # Plot line chart
    plt.figure(figsize=(12,6))
    plt.plot(months, counts, marker='o', linestyle='-', color='blue', linewidth=2)
    plt.title("Complaints Over Time", fontsize=16)
    plt.xlabel("Month", fontsize=14)
    plt.ylabel("Number of Complaints", fontsize=14)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Save graph in static folder
    if not os.path.exists("static"):
        os.makedirs("static")
    graph_path = "static/complaints_graph.png"
    plt.savefig(graph_path)
    plt.close()

    return render_template("complaint_analysis.html", graph_url="/"+graph_path)


# ---------------- Complaint Bar Graph -----------------
@app.route("/complaints_bar_graph")
def complaints_bar_graph():
    if "role" not in session or session["role"] != "admin":
        return redirect("/admin")
    
    db = get_db()
    cursor = db.cursor()
    
    # Get complaints grouped by month
    cursor.execute("""
        SELECT applied_time, COUNT(*) 
        FROM complaints
        GROUP BY YEAR(applied_time), MONTH(applied_time)
        ORDER BY YEAR(applied_time), MONTH(applied_time)
    """)
    data = cursor.fetchall()
    db.close()

    # Initialize all months with 0
    import calendar
    months = list(calendar.month_name)[1:]  # ['January', 'February', ... 'December']
    counts_dict = {month: 0 for month in months}

    # Fill counts from DB
    from datetime import datetime
    for row in data:
        dt = row[0] if isinstance(row[0], datetime) else datetime.strptime(str(row[0]), "%Y-%m-%d %H:%M:%S")
        month_name = dt.strftime("%B")
        counts_dict[month_name] = row[1]

    counts = [counts_dict[m] for m in months]

    # Prepare 2 columns: first 6 months and last 6 months
    left_data = list(zip(months[:6], counts[:6]))   # January to June
    right_data = list(zip(months[6:], counts[6:]))  # July to December

    # Plot Bar Graph
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10,5))
    plt.bar(months, counts, color='skyblue')
    plt.title("Complaints Month-wise")
    plt.xlabel("Month")
    plt.ylabel("Number of Complaints")
    plt.xticks(rotation=45)
    plt.tight_layout()

    import os
    image_path = "static/complaints_bar_graph.png"
    plt.savefig(image_path)
    plt.close()

   

    return render_template("admin_home.html", bar_graph_url=image_path, left_data=left_data,
    right_data=right_data
)
# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- RUN APP ----------------
if __name__=="__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)
