from database.db_manager import seed_demo_customers, seed_initial_admin


if __name__ == "__main__":
    seed_demo_customers()
    seed_initial_admin()
    print("Demo customer records are ready.")
