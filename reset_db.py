from app import app, db
import os

with app.app_context():
    # Delete the old database file if it exists
    db_path = os.path.join(app.instance_path, 'site.db')
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Deleted old database at {db_path}")
    
    # Create all tables with the new schema
    db.create_all()
    print("Database tables recreated successfully.")
