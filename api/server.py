import sys
import os
from flask import Flask, jsonify, render_template
import sqlite3
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from database_service import DatabaseService

app = Flask(__name__)

DB_PATH = "edge.db"


db=DatabaseService(db_path=DB_PATH)


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/today")
def today_data():
    rows = db.get_today_measurements()
   

    data = []

    for r in rows:
        data.append({
            "timestamp": r[0],
            "water_level": r[1],
            "liquid_level": r[2]
        })

    return jsonify(data)


app.run(host="0.0.0.0", port=5000)