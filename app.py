import os
import time
from functools import wraps

import cloudinary
import cloudinary.uploader

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from models import (
    create_tables, insert_default_categories, ensure_category_exists,
    create_user, login_user, create_provider, update_provider,
    update_provider_image, get_all_categories, get_all_providers,
    get_provider_by_id, get_provider_by_user_id, get_user_by_id,
    get_recent_providers, search_providers,
    increment_provider_views,
    toggle_favorite, is_favorited, get_user_favorites, get_favorite_ids,
    submit_review, get_provider_reviews, get_review_stats, get_user_review_for_provider,
    send_inquiry, get_provider_inquiries, mark_inquiry_read, get_unread_inquiry_count,
    get_providers_count, get_provider_stats,
    update_user_profile, update_user_password, activate_provider_subscription, delete_user_account,
    get_provider_images, add_provider_image, delete_provider_image
)

app = Flask(__name__)
app.config.from_object(Config)

# Configure Cloudinary securely (reads CLOUDINARY_URL from env)
cloudinary.config(
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key = os.getenv('CLOUDINARY_API_KEY'),
    api_secret = os.getenv('CLOUDINARY_API_SECRET'),
    secure = True
)

# Centralized branding management variables configuration
GLOBAL_LOGO_URL = "https://i.ibb.co/NdT4FJtJ/Chat-GPT-Image-Jul-14-2026-04-01-18-PM-1-removebg-preview.png"

@app.context_processor
def utility_processor():
    return dict(
        max=max, 
        min=min, 
        round=round, 
        razorpay_key_id=app.config['RAZORPAY_KEY_ID'],
        logo_url=GLOBAL_LOGO_URL
    )


# Temp folder is created by config now
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

create_tables()
insert_default_categories()

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'error')
            return redirect(url_for('auth'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    categories = get_all_categories()
    recent_providers = get_recent_providers(8)
    fav_ids = get_favorite_ids(session['user_id']) if 'user_id' in session else []
    return render_template(
        'index.html',
        categories=categories,
        providers=recent_providers,
        favorite_ids=fav_ids
    )


@app.route('/auth')
def auth():
    if 'user_id' in session:
        return redirect(url_for('profile'))
    categories = get_all_categories()
    return render_template('auth.html', categories=categories, hide_nav=True)


@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')

    if not email or not password:
        flash('Please provide your complete credentials.', 'error')
        return redirect(url_for('auth'))

    user = login_user(email)
    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['account_type'] = user['account_type']
        flash('Welcome back to PeopleConnect!', 'success')
        return redirect(url_for('profile'))

    flash('Invalid credentials. Please try again.', 'error')
    return redirect(url_for('auth'))


@app.route('/register', methods=['POST'])
def register():
    account_type = request.form.get('account_type', 'user')
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not name or not email or not phone or not password or not confirm_password:
        flash('All fields are required.', 'error')
        return redirect(url_for('auth'))

    if len(password) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(url_for('auth'))

    if password != confirm_password:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('auth'))

    category = ''
    if account_type == 'provider':
        business_name = request.form.get('business_name', '').strip()
        category_select = request.form.get('category', '').strip()
        custom_category = request.form.get('custom_category', '').strip()
        city = request.form.get('city', '').strip()
        area = request.form.get('area', '').strip()
        provider_phone = request.form.get('provider_phone', '').strip()

        if category_select == '__OTHER__':
            category = ensure_category_exists(custom_category) if custom_category else "Other"
        else:
            category = category_select

        if not business_name or not category or not city or not area or not provider_phone:
            flash('Please fill all provider fields.', 'error')
            return redirect(url_for('auth'))

    hashed_password = generate_password_hash(password)
    user_id = create_user(name, email, phone, hashed_password, account_type)

    if user_id is None:
        flash('Email already registered.', 'error')
        return redirect(url_for('auth'))

    if account_type == 'provider':
        experience = request.form.get('experience', '').strip()
        description = request.form.get('description', '').strip()
        address = request.form.get('address', '').strip()

        profile_image = None
        profile_image_public_id = None
        
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename != '' and allowed_file(file.filename):
                # Upload to Cloudinary
                upload_result = cloudinary.uploader.upload(
                    file,
                    folder="peopleconnect/profiles/",
                    public_id=f"provider_{user_id}_{int(time.time())}",
                    overwrite=True,
                    resource_type="image"
                )
                profile_image = upload_result.get('secure_url')
                profile_image_public_id = upload_result.get('public_id')

        business_images = []
        if 'business_images' in request.files:
            files = request.files.getlist('business_images')
            for idx, file in enumerate(files):
                if file and file.filename != '' and allowed_file(file.filename):
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder="peopleconnect/providers/",
                        public_id=f"biz_{user_id}_{int(time.time() * 1000)}_{idx}",
                        overwrite=True,
                        resource_type="image"
                    )
                    business_images.append((upload_result.get('secure_url'), upload_result.get('public_id')))

        create_provider(
            user_id, business_name, category, experience,
            description, city, area, address, provider_phone, 
            profile_image, profile_image_public_id, business_images
        )

        session['user_id'] = user_id
        session['user_name'] = name
        session['account_type'] = account_type

        flash('Account generated successfully. Complete subscription checkout to activate your business visibility dashboard!', 'success')
        return redirect(url_for('profile', trigger_checkout='true'))

    flash('Registration successful! Please sign in.', 'success')
    return redirect(url_for('auth'))


@app.route('/api/subscription/verify', methods=['POST'])
@login_required
def verify_subscription_payment():
    razorpay_payment_id = request.json.get('razorpay_payment_id')
    if razorpay_payment_id:
        activate_provider_subscription(session['user_id'])
        return jsonify({'status': 'success', 'message': 'Subscription verified successfully!'})
    return jsonify({'status': 'failed', 'message': 'Payment validation checks dropped.'}), 400


@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    password = request.form.get('delete_password', '')
    user = get_user_by_id(session['user_id'])

    if not password or not check_password_hash(user['password'], password):
        flash('Incorrect password. Account erasure request denied.', 'error')
        return redirect(url_for('edit_profile_page', tab='security'))

    success = delete_user_account(session['user_id'])
    if success:
        session.clear()
        flash('Your account and all associated data have been permanently deleted.', 'success')
        return redirect(url_for('index'))
    else:
        flash('An internal system error occurred. Account erasure failed.', 'error')
        return redirect(url_for('edit_profile_page'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))


@app.route('/profile')
@login_required
def profile():
    user = get_user_by_id(session['user_id'])
    provider = None
    provider_stats = None
    inquiries = []
    unread_count = 0
    if session['account_type'] == 'provider':
        provider = get_provider_by_user_id(session['user_id'])
        inquiries = get_provider_inquiries(session['user_id'])
        unread_count = get_unread_inquiry_count(session['user_id'])
        provider_stats = get_provider_stats(session['user_id'])

    categories = get_all_categories()
    recent_providers = get_recent_providers(6)

    return render_template(
        'profile.html',
        user=user,
        provider=provider,
        categories=categories,
        providers=recent_providers,
        unread_count=unread_count,
        provider_stats=provider_stats,
        trigger_checkout=request.args.get('trigger_checkout', 'false')
    )


@app.route('/edit-profile')
@login_required
def edit_profile_page():
    user = get_user_by_id(session['user_id'])
    provider = None
    business_images = []
    if session['account_type'] == 'provider':
        provider = get_provider_by_user_id(session['user_id'])
        if provider:
            business_images = get_provider_images(provider['id'])
    categories = get_all_categories()
    return render_template(
        'edit_profile.html',
        user=user,
        provider=provider,
        categories=categories,
        business_images=business_images
    )


@app.route('/providers')
def providers():
    category = request.args.get('category', '')
    search_query = request.args.get('search', '')
    sort = request.args.get('sort', 'newest')
    page = request.args.get('page', 1, type=int)
    per_page = 12

    if page < 1:
        page = 1

    if search_query:
        total = get_providers_count(search_query=search_query)
        provider_list = search_providers(search_query, limit=per_page, offset=(page - 1) * per_page, sort=sort)
    elif category:
        total = get_providers_count(category=category)
        provider_list = get_all_providers(category, limit=per_page, offset=(page - 1) * per_page, sort=sort)
    else:
        total = get_providers_count()
        provider_list = get_all_providers(limit=per_page, offset=(page - 1) * per_page, sort=sort)

    total_pages = max(1, (total + per_page - 1) // per_page)

    categories = get_all_categories()
    fav_ids = get_favorite_ids(session['user_id']) if 'user_id' in session else []
    return render_template(
        'providers.html',
        providers=provider_list,
        categories=categories,
        selected_category=category,
        search_query=search_query,
        favorite_ids=fav_ids,
        page=page,
        total_pages=total_pages,
        sort=sort,
        total=total
    )


@app.route('/provider/<int:provider_id>')
def provider_details(provider_id):
    provider = get_provider_by_id(provider_id)
    if not provider or (provider['is_subscribed'] == 0 and ('user_id' not in session or session['user_id'] != provider['user_id'])):
        flash('The selected business listing profile parameter is unavailable or pending subscription activation.', 'error')
        return redirect(url_for('providers'))

    increment_provider_views(provider_id)
    provider = get_provider_by_id(provider_id)
    business_images = get_provider_images(provider_id)
    reviews = get_provider_reviews(provider_id)
    stats, breakdown = get_review_stats(provider_id)

    user_review = None
    is_fav = False
    if 'user_id' in session:
        user_review = get_user_review_for_provider(session['user_id'], provider_id)
        is_fav = is_favorited(session['user_id'], provider_id)

    return render_template(
        'provider_details.html',
        provider=provider,
        business_images=business_images,
        reviews=reviews,
        stats=stats,
        breakdown=breakdown,
        user_review=user_review,
        is_favorited=is_fav
    )


@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    if session['account_type'] != 'provider':
        flash('Only providers can update business profiles.', 'error')
        return redirect(url_for('edit_profile_page'))

    business_name = request.form.get('business_name', '').strip()
    category_select = request.form.get('category', '').strip()
    custom_category = request.form.get('custom_category', '').strip()
    experience = request.form.get('experience', '').strip()
    description = request.form.get('description', '').strip()
    city = request.form.get('city', '').strip()
    area = request.form.get('area', '').strip()
    address = request.form.get('address', '').strip()
    phone = request.form.get('phone', '').strip()

    if category_select == '__OTHER__':
        category = ensure_category_exists(custom_category) if custom_category else "Other"
    else:
        category = category_select

    if not business_name or not category or not city or not area or not phone:
        flash('Required fields are missing.', 'error')
        return redirect(url_for('edit_profile_page'))

    if 'profile_image' in request.files:
        file = request.files['profile_image']
        if file and file.filename != '' and allowed_file(file.filename):
            # Delete old image from Cloudinary if public_id exists
            provider = get_provider_by_user_id(session['user_id'])
            if provider and provider.get('profile_image_public_id'):
                try:
                    cloudinary.uploader.destroy(provider['profile_image_public_id'])
                except Exception:
                    pass # Ignore deletion errors

            upload_result = cloudinary.uploader.upload(
                file,
                folder="peopleconnect/profiles/",
                public_id=f"provider_{session['user_id']}_{int(time.time())}",
                overwrite=True,
                resource_type="image"
            )
            update_provider_image(session['user_id'], upload_result.get('secure_url'), upload_result.get('public_id'))

    if 'business_images' in request.files:
        provider = get_provider_by_user_id(session['user_id'])
        if provider:
            files = request.files.getlist('business_images')
            for idx, file in enumerate(files):
                if file and file.filename != '' and allowed_file(file.filename):
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder="peopleconnect/providers/",
                        public_id=f"biz_{session['user_id']}_{int(time.time() * 1000)}_{idx}",
                        overwrite=True,
                        resource_type="image"
                    )
                    add_provider_image(provider['id'], upload_result.get('secure_url'), upload_result.get('public_id'))

    update_provider(
        session['user_id'], business_name, category, experience,
        description, city, area, address, phone
    )

    flash('Business profile updated successfully.', 'success')
    return redirect(url_for('edit_profile_page'))


@app.route('/delete-business-image', methods=['POST'])
@login_required
def delete_business_image():
    image_id = request.form.get('image_id', type=int)
    if not image_id:
        return jsonify({'error': 'Missing image_id'}), 400

    # Get public ID before deleting from DB
    public_id = delete_provider_image(image_id, session['user_id'])
    
    # Delete from Cloudinary
    if public_id:
        try:
            cloudinary.uploader.destroy(public_id)
        except Exception:
            pass
            
    return jsonify({'ok': True})


@app.route('/edit-user-profile', methods=['POST'])
@login_required
def edit_user_profile():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()

    if not name or not email:
        flash('Name and email are required.', 'error')
        return redirect(url_for('edit_profile_page'))

    success = update_user_profile(session['user_id'], name, phone, email)
    if success:
        session['user_name'] = name
        flash('Personal profile updated.', 'success')
    else:
        flash('That email is already in use.', 'error')

    return redirect(url_for('edit_profile_page'))


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current = request.form.get('current_password', '')
    new_pass = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    if not current or not new_pass or not confirm:
        flash('All password fields are required.', 'error')
        return redirect(url_for('edit_profile_page'))

    if len(new_pass) < 6:
        flash('New password must be at least 6 characters.', 'error')
        return redirect(url_for('edit_profile_page'))

    if new_pass != confirm:
        flash('New passwords do not match.', 'error')
        return redirect(url_for('edit_profile_page'))

    user = get_user_by_id(session['user_id'])
    if not check_password_hash(user['password'], current):
        flash('Current password is incorrect.', 'error')
        return redirect(url_for('edit_profile_page'))

    update_user_password(session['user_id'], generate_password_hash(new_pass))
    flash('Password changed successfully.', 'success')
    return redirect(url_for('edit_profile_page'))


@app.route('/favorites')
@login_required
def favorites():
    fav_providers = get_user_favorites(session['user_id'])
    return render_template(
        'favorites.html',
        providers=fav_providers
    )


@app.route('/toggle-favorite', methods=['POST'])
@login_required
def toggle_favorite_route():
    provider_id = request.form.get('provider_id', type=int)
    if not provider_id:
        return jsonify({'error': 'Missing provider_id'}), 400

    added = toggle_favorite(session['user_id'], provider_id)
    return jsonify({'favorited': added})


@app.route('/submit-review', methods=['POST'])
@login_required
def submit_review_route():
    provider_id = request.form.get('provider_id', type=int)
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    if not provider_id or not rating or rating < 1 or rating > 5:
        flash('Please select a valid rating.', 'error')
        return redirect(request.referrer or url_for('index'))

    provider = get_provider_by_id(provider_id)
    if not provider:
        flash('Provider not found.', 'error')
        return redirect(url_for('providers'))

    if provider['user_id'] == session['user_id']:
        flash('You cannot review your own business.', 'error')
        return redirect(url_for('provider_details', provider_id=provider_id))

    submit_review(provider_id, session['user_id'], rating, comment)
    flash('Review submitted successfully!', 'success')
    return redirect(url_for('provider_details', provider_id=provider_id))


@app.route('/send-inquiry', methods=['POST'])
@login_required
def send_inquiry_route():
    provider_id = request.form.get('provider_id', type=int)
    message = request.form.get('message', '').strip()

    if not provider_id or not message:
        flash('Please write a message.', 'error')
        return redirect(request.referrer or url_for('index'))

    user = get_user_by_id(session['user_id'])
    send_inquiry(provider_id, session['user_id'], user['name'], user['phone'] or '', message)
    flash('Inquiry sent to the service provider!', 'success')
    return redirect(url_for('provider_details', provider_id=provider_id))


@app.route('/mark-inquiry-read/<int:inquiry_id>', methods=['POST'])
@login_required
def mark_inquiry_read_route(inquiry_id):
    mark_inquiry_read(inquiry_id)
    return jsonify({'ok': True})


@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])

    providers = search_providers(query)
    result = [{
        'id': p['id'],
        'business_name': p['business_name'],
        'owner_name': p['owner_name'],
        'category': p['category'],
        'city': p['city'],
        'area': p['area'],
        'phone': p['phone'],
        'profile_image': p['profile_image']
    } for p in providers]
    return jsonify(result)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Check if filename is actually a full Cloudinary URL (for backward compatibility)
    if filename.startswith('http'):
        return redirect(filename)
    
    # Otherwise try to serve from local temp folder (legacy support)
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
