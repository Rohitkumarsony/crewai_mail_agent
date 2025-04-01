import mysql.connector

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="E-commerce_query"
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

def create_tables():
    conn = get_db_connection()
    if conn is None:
        print("❌ Failed to connect to database.")
        return

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers_query (
            id INT AUTO_INCREMENT PRIMARY KEY,
            customer_name VARCHAR(255),
            email VARCHAR(255) UNIQUE,
            address TEXT,
            user_message TEXT,
            agent_mail  TEXT,
            refund_requested TEXT,
            status ENUM('in_progress', 'solved'),
            product_issue TEXT,
            order_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        );
    """)

    print("✅ Tables created successfully!")
    conn.commit()
    cursor.close()
    conn.close()


def insert_partial_customer_query(email, customer_name=None, address=None, user_message=None, agent_mail=None, refund_requested=None, product_issue=None, order_id=None):
    """Insert or update customer query data."""
    conn = get_db_connection()
    if conn is None:
        print("❌ Failed to connect to database.")
        return {"status": "error", "message": "Database connection failed."}

    try:
        cursor = conn.cursor()

        query = """
            INSERT INTO customers_query (email, customer_name, address, user_message, agent_mail, refund_requested, status, product_issue, order_id)
            VALUES (%s, %s, %s, %s, %s, %s, 'in_progress', %s, %s)
            ON DUPLICATE KEY UPDATE 
                customer_name = COALESCE(%s, customer_name),
                address = COALESCE(%s, address),
                user_message = COALESCE(%s, user_message),
                agent_mail = COALESCE(%s, agent_mail),
                refund_requested = COALESCE(%s, refund_requested),
                product_issue = COALESCE(%s, product_issue),
                order_id = COALESCE(%s, order_id),
                updated_at = CURRENT_TIMESTAMP
        """

        values = (
            email, customer_name, address, user_message, agent_mail, refund_requested, product_issue, order_id,
            customer_name, address, user_message, agent_mail, refund_requested, product_issue, order_id
        )

        cursor.execute(query, values)
        conn.commit()

        print(f"✅ Data inserted/updated for email: {email}")
        return {"status": "success", "message": "Data inserted/updated successfully."}
    except mysql.connector.Error as err:
        print(f"❌ Error: {err}")
        return {"status": "error", "message": str(err)}
    finally:
        cursor.close()
        conn.close()


def update_customer_query(email, **kwargs):
    """Update customer query fields dynamically."""
    conn = get_db_connection()
    if conn is None:
        print("❌ Failed to connect to database.")
        return {"status": "error", "message": "Database connection failed."}

    try:
        cursor = conn.cursor()

        # Dynamically create SET clause
        set_clause = ", ".join(f"{key} = %s" for key in kwargs)
        query = f"UPDATE customers_query SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE email = %s"

        # Add email as the last value
        values = tuple(kwargs.values()) + (email,)

        cursor.execute(query, values)
        conn.commit()

        if cursor.rowcount > 0:
            print(f"✅ Data updated for email: {email}")
            return {"status": "success", "message": f"Updated {len(kwargs)} fields for {email}."}
        else:
            print("⚠️ No record found with the given email.")
            return {"status": "error", "message": "Email not found."}
    except mysql.connector.Error as err:
        print(f"❌ Error: {err}")
        return {"status": "error", "message": str(err)}
    finally:
        cursor.close()
        conn.close()


