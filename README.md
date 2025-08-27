# Real Estate Plot Reservation Backend

A comprehensive Django REST API backend for a real estate platform that enables property listings, user management, payment processing, and notifications.

## Features

### 🏠 Property Management
- **Listings**: Create, read, update, and delete property listings
- **Property Types**: Support for apartments, houses, condos, townhouses, and land
- **Advanced Filtering**: Filter by price, location, amenities, property type, and more
- **Geographic Data**: Latitude/longitude support for mapping
- **Image Management**: Multiple image uploads per listing
- **Points of Interest**: Nearby POI discovery within 10km radius

### 👥 User Management
- **Custom User Model**: Extended Django user with email authentication
- **User Profiles**: Agency information, contact details, and profile pictures
- **Authentication**: Token-based authentication via Djoser
- **Authorization**: Role-based access control

### 💳 Payment Processing
- **Multiple Gateways**: Flutterwave (Mobile Money) and PayPal integration
- **Reservation Fees**: Configurable reservation/viewing fees
- **Payment Tracking**: Complete payment lifecycle management
- **Webhook Support**: Real-time payment status updates

### 🔔 Notifications
- **Real-time Notifications**: User notification system
- **Event-driven**: Automatic notifications for listing events
- **Read/Unread Status**: Track notification states
- **API Endpoints**: Full CRUD operations for notifications

## Tech Stack

- **Framework**: Django 5.1.6 + Django REST Framework
- **Database**: SQLite (development) / PostgreSQL (production ready)
- **Authentication**: Token-based via Djoser
- **File Storage**: Local storage with Django's media handling
- **Payment Gateways**: Flutterwave, PayPal
- **API Documentation**: RESTful API design

## Installation

### Prerequisites
- Python 3.8+
- pip
- Virtual environment (recommended)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Real-Estate-Plot-Rervervation-backend
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Create a `.env` file in the backend directory:
   ```env
   # Email Configuration
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-app-password
   
   # Flutterwave Configuration
   FLUTTERWAVE_PUBLIC_KEY=your-flutterwave-public-key
   FLUTTERWAVE_SECRET_KEY=your-flutterwave-secret-key
   FLUTTERWAVE_ENCRYPTION_KEY=your-flutterwave-encryption-key
   
   # PayPal Configuration
   PAYPAL_CLIENT_ID=your-paypal-client-id
   PAYPAL_SECRET_KEY=your-paypal-secret-key
   PAYPAL_ENVIRONMENT=sandbox  # or 'live' for production
   
   # Stripe Configuration (if needed)
   STRIPE_PUBLISHABLE_KEY=your-stripe-publishable-key
   STRIPE_SECRET_KEY=your-stripe-secret-key
   
   # Base URL
   BASE_URL=http://localhost:8000
   ```

5. **Database Setup**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

6. **Load Sample Data** (Optional)
   ```bash
   python manage.py loaddata listings.json
   ```

7. **Create Superuser**
   ```bash
   python manage.py createsuperuser
   ```

8. **Run Development Server**
   ```bash
   python manage.py runserver
   ```

The API will be available at `http://localhost:8000/`

## API Endpoints

### Authentication
- `POST /api-auth-djoser/users/` - User registration
- `POST /api-auth-djoser/auth/token/login/` - Login
- `POST /api-auth-djoser/auth/token/logout/` - Logout

### Listings
- `GET /api/listings/` - List all listings (with filtering)
- `POST /api/listings/create/` - Create new listing (authenticated)
- `GET /api/listings/{id}/` - Get listing details
- `PUT /api/listings/{id}/update/` - Update listing (authenticated)
- `DELETE /api/listings/{id}/delete/` - Delete listing (authenticated)

### User Profiles
- `GET /api/profiles/` - List all profiles
- `GET /api/profiles/{seller_id}/` - Get profile by seller ID
- `PUT /api/profiles/{seller_id}/update/` - Update profile (authenticated)

### Payments
- `POST /api/payments/checkout/` - Initialize payment
- `POST /api/payments/paypal/create/` - Create PayPal order
- `POST /api/payments/paypal/capture/` - Capture PayPal payment
- `POST /api/payments/flutterwave/callback/` - Flutterwave callback
- `POST /api/payments/flutterwave/webhook/` - Flutterwave webhook

### Notifications
- `GET /api/notifications/` - List user notifications
- `GET /api/notifications/unread-count/` - Get unread count
- `PATCH /api/notifications/{id}/read/` - Mark as read

## API Usage Examples

### Authentication
```bash
# Register
curl -X POST http://localhost:8000/api-auth-djoser/users/ \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "email": "test@example.com", "password": "securepass123"}'

# Login
curl -X POST http://localhost:8000/api-auth-djoser/auth/token/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "securepass123"}'
```

### Listings with Filters
```bash
# Get listings with filters
curl "http://localhost:8000/api/listings/?listing_type=apartment&min_price=1000&max_price=2000&furnished=true"

# Search listings
curl "http://localhost:8000/api/listings/?search=kampala"

# Get listings with POIs
curl "http://localhost:8000/api/listings/?include_pois=1"
```

### Create Listing
```bash
curl -X POST http://localhost:8000/api/listings/create/ \
  -H "Authorization: Token your-auth-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Modern Apartment in Kololo",
    "description": "Beautiful 2-bedroom apartment",
    "price": "1500.00",
    "listing_type": "apartment",
    "bedrooms": 2,
    "bathrooms": 2,
    "furnished": true,
    "borough": "Kololo"
  }'
```

## Filtering Options

The listings API supports extensive filtering:

- **Price**: `min_price`, `max_price`
- **Property**: `bedrooms`, `bathrooms`, `listing_type`, `property_status`
- **Location**: `area`, `borough`
- **Amenities**: `furnished`, `pool`, `parking`, `cctv`, `garden`, `elevator`
- **Search**: Full-text search across title, description, borough
- **Ordering**: Sort by `price`, `date_posted`, `updated_at`

## Payment Integration

### Flutterwave (Mobile Money)
Supports UGX payments via mobile money and cards. The system automatically handles:
- Payment initialization
- Callback processing
- Webhook verification
- Status updates

### PayPal
Supports USD payments with:
- Order creation
- Payment capture
- Status tracking

## Development

### Project Structure
```
backend/
├── backend/           # Main Django project
├── listings/          # Property listings app
├── users/            # User management app
├── payments/         # Payment processing app
├── notifications/    # Notification system app
├── media/           # Uploaded files
└── manage.py        # Django management script
```

### Running Tests
```bash
python manage.py test
```

### Database Migrations
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate
```

## Deployment

### Production Settings
1. Set `DEBUG = False`
2. Configure `ALLOWED_HOSTS`
3. Use PostgreSQL database
4. Set up proper media/static file serving
5. Configure HTTPS
6. Set secure environment variables

### Environment Variables for Production
```env
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgresql://user:password@localhost/dbname
SECRET_KEY=your-very-secure-secret-key
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue in the repository
- Contact the development team

## Roadmap

- [ ] Advanced search with Elasticsearch
- [ ] Real-time chat system
- [ ] Mobile app API enhancements
- [ ] Advanced analytics dashboard
- [ ] Multi-language support
- [ ] Advanced image processing
- [ ] Integration with mapping services