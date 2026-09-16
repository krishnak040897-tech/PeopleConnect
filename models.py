import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config

def get_db_connection():
    """
    Establishes a connection to the PostgreSQL database using the DATABASE_URL.
    Uses RealDictCursor to return rows as dictionaries (compatible with existing code).
    """
    if not Config.DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    
    return psycopg2.connect(Config.DATABASE_URL, cursor_factory=RealDictCursor)


def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            password TEXT NOT NULL,
            account_type TEXT NOT NULL CHECK(account_type IN ('user', 'provider')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Providers Table
    # Added profile_image_public_id for Cloudinary deletion capability
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS providers (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            business_name TEXT NOT NULL,
            category TEXT NOT NULL,
            experience TEXT,
            description TEXT,
            city TEXT NOT NULL,
            area TEXT NOT NULL,
            address TEXT,
            phone TEXT NOT NULL,
            profile_image TEXT,
            profile_image_public_id TEXT,
            views INTEGER DEFAULT 0,
            is_subscribed INTEGER DEFAULT 0,
            subscription_started_at TIMESTAMP,
            subscription_expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Provider Images Table
    # Added public_id for Cloudinary deletion capability
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS provider_images (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            public_id TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE
        )
    ''')

    # Categories Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            category_name TEXT UNIQUE NOT NULL
        )
    ''')

    # Favorites Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            provider_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (provider_id) REFERENCES providers(id),
            UNIQUE(user_id, provider_id)
        )
    ''')

    # Reviews Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES providers(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Inquiries Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inquiries (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER NOT NULL,
            user_id INTEGER,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES providers(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()
    migrate_tables()


def migrate_tables():
    """Handles adding new columns to existing database schemas."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Helper to safely add columns
    def add_column(table, column, definition):
        try:
            cursor.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}')
            conn.commit()
        except psycopg2.Error:
            pass # Ignore errors if column already exists or other issues

    # Backward compatibility for views
    add_column('providers', 'views', 'INTEGER DEFAULT 0')
    add_column('providers', 'is_subscribed', 'INTEGER DEFAULT 0')
    add_column('providers', 'subscription_expires_at', 'TIMESTAMP')
    add_column('providers', 'subscription_started_at', 'TIMESTAMP')
    
    # New columns for Cloudinary
    add_column('providers', 'profile_image_public_id', 'TEXT')
    add_column('provider_images', 'public_id', 'TEXT')

    conn.close()


def insert_default_categories():
    categories = [
        'Doctor', 'Dentist', 'Physiotherapist', 'Plumber', 'Electrician', 
        'Beautician', 'Hair Salon', 'Carpenter', 'Mechanic', 'Tutor', 
        'Mobile Repair', 'AC Repair', 'Laptop Repair', 'Taxi Driver',
        'Packers & Movers', 'Caterer', 'Event Photographer', 'Fitness Trainer',
        'Water Supplier', 'Grocery Store', 'Restaurant', 'Hotel', 'Pharmacy',
        'Laundry Service', 'Interior Designer', 'Legal Consultant', 'Chartered Accountant'
    ]
    conn = get_db_connection()
    cursor = conn.cursor()
    for cat in categories:
        # PostgreSQL uses ON CONFLICT instead of INSERT OR IGNORE
        cursor.execute('''
            INSERT INTO categories (category_name) VALUES (%s) 
            ON CONFLICT (category_name) DO NOTHING
        ''', (cat.strip(),))
    conn.commit()
    conn.close()


def ensure_category_exists(category_name):
    cleaned_name = category_name.strip()
    if not cleaned_name:
        return "Other"
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO categories (category_name) VALUES (%s) 
        ON CONFLICT (category_name) DO NOTHING
    ''', (cleaned_name,))
    conn.commit()
    conn.close()
    return cleaned_name


# ── User functions ──

def create_user(name, email, phone, password, account_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (name, email, phone, password, account_type) 
            VALUES (%s, %s, %s, %s, %s) 
            RETURNING id
        ''', (name, email, phone, password, account_type))
        user_id = cursor.fetchone()['id']
        conn.commit()
        return user_id
    except psycopg2.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def login_user(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
    user = cursor.fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user


def update_user_profile(user_id, name, phone, email):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE users SET name = %s, phone = %s, email = %s 
            WHERE id = %s
        ''', (name, phone, email, user_id))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False
    finally:
        conn.close()


def update_user_password(user_id, new_password_hash):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET password = %s WHERE id = %s', (new_password_hash, user_id))
    conn.commit()
    conn.close()


def delete_user_account(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Foreign key constraints usually handle cascading deletes if set up,
        # but manual deletion ensures everything goes if constraints are not ON DELETE CASCADE
        cursor.execute('SELECT id FROM providers WHERE user_id = %s', (user_id,))
        provider = cursor.fetchone()
        if provider:
            provider_id = provider['id']
            # Note: Actual Cloudinary images deletion should happen in app.py or via a trigger logic hook,
            # here we are just removing DB records.
            cursor.execute('DELETE FROM provider_images WHERE provider_id = %s', (provider_id,))
            cursor.execute('DELETE FROM reviews WHERE provider_id = %s', (provider_id,))
            cursor.execute('DELETE FROM inquiries WHERE provider_id = %s', (provider_id,))
            cursor.execute('DELETE FROM favorites WHERE provider_id = %s', (provider_id,))
            cursor.execute('DELETE FROM providers WHERE id = %s', (provider_id,))
        
        cursor.execute('DELETE FROM favorites WHERE user_id = %s', (user_id,))
        cursor.execute('DELETE FROM reviews WHERE user_id = %s', (user_id,))
        cursor.execute('DELETE FROM inquiries WHERE user_id = %s', (user_id,))
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


# ── Provider functions ──

def create_provider(user_id, business_name, category, experience, description, city, area, address, phone, profile_image, profile_image_public_id=None, business_images=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO providers 
        (user_id, business_name, category, experience, description, city, area, address, phone, profile_image, profile_image_public_id, is_subscribed)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
        RETURNING id
    ''', (user_id, business_name, category, experience, description, city, area, address, phone, profile_image, profile_image_public_id))
    
    provider_id = cursor.fetchone()['id']

    if business_images:
        # business_images is expected to be a list of tuples: (url, public_id)
        for idx, (img_path, public_id) in enumerate(business_images):
            cursor.execute('''
                INSERT INTO provider_images (provider_id, image_path, public_id, sort_order) 
                VALUES (%s, %s, %s, %s)
            ''', (provider_id, img_path, public_id, idx))

    conn.commit()
    conn.close()
    return provider_id


def update_provider(user_id, business_name, category, experience, description, city, area, address, phone):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE providers
        SET business_name = %s, category = %s, experience = %s, description = %s, 
            city = %s, area = %s, address = %s, phone = %s
        WHERE user_id = %s
    ''', (business_name, category, experience, description, city, area, address, phone, user_id))
    conn.commit()
    conn.close()


def activate_provider_subscription(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # PostgreSQL uses NOW() or CURRENT_TIMESTAMP
    cursor.execute('''
        UPDATE providers 
        SET is_subscribed = 1, 
            subscription_started_at = NOW(),
            subscription_expires_at = NOW() + INTERVAL '30 days' 
        WHERE user_id = %s
    ''', (user_id,))
    conn.commit()
    conn.close()


def update_provider_image(user_id, image_path, public_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE providers 
        SET profile_image = %s, profile_image_public_id = %s 
        WHERE user_id = %s
    ''', (image_path, public_id, user_id))
    conn.commit()
    conn.close()


# ── Provider Images functions ──

def add_provider_image(provider_id, image_path, public_id=None, sort_order=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if sort_order is None:
        cursor.execute('''
            SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order 
            FROM provider_images WHERE provider_id = %s
        ''', (provider_id,))
        sort_order = cursor.fetchone()['next_order']
        
    cursor.execute('''
        INSERT INTO provider_images (provider_id, image_path, public_id, sort_order) 
        VALUES (%s, %s, %s, %s)
    ''', (provider_id, image_path, public_id, sort_order))
    conn.commit()
    conn.close()


def get_provider_images(provider_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM provider_images 
        WHERE provider_id = %s 
        ORDER BY sort_order ASC, id ASC
    ''', (provider_id,))
    images = cursor.fetchall()
    conn.close()
    return images


def delete_provider_image(image_id, provider_user_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if provider_user_id:
        cursor.execute('''
            DELETE FROM provider_images 
            WHERE id = %s AND provider_id IN (
                SELECT id FROM providers WHERE user_id = %s
            )
            RETURNING public_id
        ''', (image_id, provider_user_id))
    else:
        cursor.execute('DELETE FROM provider_images WHERE id = %s RETURNING public_id', (image_id,))
    
    # Return the public_id so the app can delete from Cloudinary
    row = cursor.fetchone()
    public_id = row['public_id'] if row else None
    
    conn.commit()
    conn.close()
    return public_id


def reorder_provider_images(provider_id, image_ids_ordered):
    conn = get_db_connection()
    cursor = conn.cursor()
    for idx, img_id in enumerate(image_ids_ordered):
        cursor.execute('''
            UPDATE provider_images SET sort_order = %s 
            WHERE id = %s AND provider_id = %s
        ''', (idx, img_id, provider_id))
    conn.commit()
    conn.close()


# ── Category functions ──

def get_all_categories():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM categories ORDER BY category_name ASC')
    categories = cursor.fetchall()
    conn.close()
    return categories


# ── Provider query functions ──

def get_all_providers(category=None, limit=None, offset=0, sort='newest'):
    conn = get_db_connection()
    cursor = conn.cursor()
    where_clause = " WHERE p.is_subscribed = 1"
    params = []
    if category:
        where_clause += " AND p.category = %s"
        params.append(category)
        
    if sort == 'views':
        order_clause = " ORDER BY p.views DESC, p.created_at DESC"
    elif sort == 'name':
        order_clause = " ORDER BY p.business_name ASC"
    elif sort == 'rating':
        order_clause = " ORDER BY avg_rating DESC NULLS LAST, review_count DESC"
    else:
        order_clause = " ORDER BY p.created_at DESC"
        
    limit_clause = ""
    if limit is not None:
        limit_clause = " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
    query = f'''
        SELECT p.*, u.name AS owner_name, u.email AS owner_email,
               COALESCE(AVG(r.rating), 0.0) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM providers p
        JOIN users u ON p.user_id = u.id
        LEFT JOIN reviews r ON p.id = r.provider_id
        {where_clause}
        GROUP BY p.id, u.id
        {order_clause}{limit_clause}
    '''
    cursor.execute(query, params)
    providers = cursor.fetchall()
    conn.close()
    return providers


def get_recent_providers(limit=8):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.name AS owner_name, u.email AS owner_email,
               COALESCE(AVG(r.rating), 0.0) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM providers p
        JOIN users u ON p.user_id = u.id 
        LEFT JOIN reviews r ON p.id = r.provider_id
        WHERE p.is_subscribed = 1 
        GROUP BY p.id, u.id
        ORDER BY p.created_at DESC LIMIT %s
    ''', (limit,))
    providers = cursor.fetchall()
    conn.close()
    return providers


def get_provider_by_id(provider_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.name AS owner_name, u.email AS owner_email,
               COALESCE(AVG(r.rating), 0.0) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM providers p
        JOIN users u ON p.user_id = u.id 
        LEFT JOIN reviews r ON p.id = r.provider_id
        WHERE p.id = %s
        GROUP BY p.id, u.id
    ''', (provider_id,))
    provider = cursor.fetchone()
    conn.close()
    return provider


def get_provider_by_user_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.email AS owner_email, 
               COALESCE(AVG(r.rating), 0.0) AS avg_rating, 
               COUNT(r.id) AS review_count
        FROM providers p
        JOIN users u ON p.user_id = u.id
        LEFT JOIN reviews r ON p.id = r.provider_id
        WHERE p.user_id = %s
        GROUP BY p.id, u.id
    ''', (user_id,))
    provider = cursor.fetchone()
    conn.close()
    return provider


def search_providers(query, limit=None, offset=0, sort='newest'):
    conn = get_db_connection()
    cursor = conn.cursor()
    term = f'%{query}%'
    
    if sort == 'views':
        order_clause = " ORDER BY p.views DESC, p.created_at DESC"
    elif sort == 'name':
        order_clause = " ORDER BY p.business_name ASC"
    elif sort == 'rating':
        order_clause = " ORDER BY avg_rating DESC NULLS LAST, review_count DESC"
    else:
        order_clause = " ORDER BY p.created_at DESC"
        
    limit_clause = ""
    # Postgres uses %s for placeholders
    params = [term, term, term, term, term]
    if limit is not None:
        limit_clause = " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
    cursor.execute(f'''
        SELECT p.*, u.name AS owner_name, u.email AS owner_email,
               COALESCE(AVG(r.rating), 0.0) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM providers p
        JOIN users u ON p.user_id = u.id
        LEFT JOIN reviews r ON p.id = r.provider_id
        WHERE p.is_subscribed = 1 AND (p.business_name LIKE %s OR u.name LIKE %s OR p.category LIKE %s OR p.city LIKE %s OR p.area LIKE %s)
        GROUP BY p.id, u.id
        {order_clause}{limit_clause}
    ''', params)
    providers = cursor.fetchall()
    conn.close()
    return providers


def get_providers_count(category=None, search_query=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if search_query:
        term = f'%{search_query}%'
        cursor.execute('''
            SELECT COUNT(DISTINCT p.id) as cnt FROM providers p
            JOIN users u ON p.user_id = u.id
            WHERE p.is_subscribed = 1 AND (p.business_name LIKE %s OR u.name LIKE %s OR p.category LIKE %s OR p.city LIKE %s OR p.area LIKE %s)
        ''', (term, term, term, term, term))
    elif category:
        cursor.execute('SELECT COUNT(*) as cnt FROM providers WHERE is_subscribed = 1 AND category = %s', (category,))
    else:
        cursor.execute('SELECT COUNT(*) as cnt FROM providers WHERE is_subscribed = 1')
    count = cursor.fetchone()['cnt']
    conn.close()
    return count


def increment_provider_views(provider_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE providers SET views = views + 1 WHERE id = %s', (provider_id,))
    conn.commit()
    conn.close()


def get_provider_stats(provider_user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT views, id FROM providers WHERE user_id = %s', (provider_user_id,))
    provider = cursor.fetchone()
    stats = {'views': 0, 'reviews': 0, 'inquiries': 0, 'favorites': 0}
    if provider:
        stats['views'] = provider['views'] or 0
        cursor.execute('SELECT COUNT(*) as cnt FROM reviews WHERE provider_id = %s', (provider['id'],))
        stats['reviews'] = cursor.fetchone()['cnt']
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM inquiries i
            JOIN providers p ON i.provider_id = p.id WHERE p.user_id = %s
        ''', (provider_user_id,))
        stats['inquiries'] = cursor.fetchone()['cnt']
        cursor.execute('SELECT COUNT(*) as cnt FROM favorites WHERE provider_id = %s', (provider['id'],))
        stats['favorites'] = cursor.fetchone()['cnt']
    conn.close()
    return stats


# ── Favorites ──

def toggle_favorite(user_id, provider_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM favorites WHERE user_id = %s AND provider_id = %s', (user_id, provider_id))
    existing = cursor.fetchone()
    if existing:
        cursor.execute('DELETE FROM favorites WHERE id = %s', (existing['id'],))
        conn.commit()
        conn.close()
        return False
    else:
        cursor.execute('INSERT INTO favorites (user_id, provider_id) VALUES (%s, %s)', (user_id, provider_id))
        conn.commit()
        conn.close()
        return True


def is_favorited(user_id, provider_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM favorites WHERE user_id = %s AND provider_id = %s', (user_id, provider_id))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_user_favorites(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.name AS owner_name, u.email AS owner_email,
               COALESCE(AVG(r.rating), 0.0) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM favorites f
        JOIN providers p ON f.provider_id = p.id
        JOIN users u ON p.user_id = u.id
        LEFT JOIN reviews r ON p.id = r.provider_id
        WHERE f.user_id = %s AND p.is_subscribed = 1 
        GROUP BY p.id, u.id
        ORDER BY MAX(f.created_at) DESC
    ''', (user_id,))
    providers = cursor.fetchall()
    conn.close()
    return providers


def get_favorite_ids(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT provider_id FROM favorites WHERE user_id = %s', (user_id,))
    ids = [row['provider_id'] for row in cursor.fetchall()]
    conn.close()
    return ids


# ── Reviews ──

def submit_review(provider_id, user_id, rating, comment):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM reviews WHERE provider_id = %s AND user_id = %s', (provider_id, user_id))
    if cursor.fetchone():
        cursor.execute('''
            UPDATE reviews SET rating = %s, comment = %s, created_at = CURRENT_TIMESTAMP 
            WHERE provider_id = %s AND user_id = %s
        ''', (rating, comment, provider_id, user_id))
    else:
        cursor.execute('''
            INSERT INTO reviews (provider_id, user_id, rating, comment) 
            VALUES (%s, %s, %s, %s)
        ''', (provider_id, user_id, rating, comment))
    conn.commit()
    conn.close()


def get_provider_reviews(provider_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, u.name AS reviewer_name FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.provider_id = %s ORDER BY r.created_at DESC
    ''', (provider_id,))
    reviews = cursor.fetchall()
    conn.close()
    return reviews


def get_review_stats(provider_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) as total, COALESCE(AVG(rating),0.0) as average 
        FROM reviews WHERE provider_id = %s
    ''', (provider_id,))
    stats = cursor.fetchone()
    cursor.execute('''
        SELECT rating, COUNT(*) as count FROM reviews WHERE provider_id = %s
        GROUP BY rating ORDER BY rating DESC
    ''', (provider_id,))
    breakdown = {row['rating']: row['count'] for row in cursor.fetchall()}
    conn.close()
    return stats, breakdown


def get_user_review_for_provider(user_id, provider_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM reviews WHERE user_id = %s AND provider_id = %s', (user_id, provider_id))
    row = cursor.fetchone()
    conn.close()
    return row


# ── Inquiries ──

def send_inquiry(provider_id, user_id, name, phone, message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO inquiries (provider_id, user_id, name, phone, message) 
        VALUES (%s, %s, %s, %s, %s)
    ''', (provider_id, user_id, name, phone, message))
    conn.commit()
    conn.close()


def get_provider_inquiries(provider_user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT i.* FROM inquiries i
        JOIN providers p ON i.provider_id = p.id
        WHERE p.user_id = %s ORDER BY i.created_at DESC
    ''', (provider_user_id,))
    inquiries = cursor.fetchall()
    conn.close()
    return inquiries


def mark_inquiry_read(inquiry_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE inquiries SET is_read = 1 WHERE id = %s', (inquiry_id,))
    conn.commit()
    conn.close()


def get_unread_inquiry_count(provider_user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) as cnt FROM inquiries i
        JOIN providers p ON i.provider_id = p.id
        WHERE p.user_id = %s AND i.is_read = 0
    ''', (provider_user_id,))
    row = cursor.fetchone()
    count = row['cnt'] if row else 0
    conn.close()
    return count
