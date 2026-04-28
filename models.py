"""Database models for Craft Connect."""
import json
from types import SimpleNamespace

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User model for login/signup."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # Profile fields
    phone = db.Column(db.String(20), nullable=True)
    profile_image = db.Column(db.String(255), nullable=True, default='default.jpg')
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)

    # Relationship to Order
    orders = db.relationship('Order', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Order(db.Model):
    """Single Order model: supports both OrderItem lines and items_json (e.g. place_order)."""
    __tablename__ = "orders"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    order_number = db.Column(db.String(20), unique=True, nullable=True)  # e.g. OD12345 (optional for place_order path)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default="Placed")
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    delivery_address = db.Column(db.Text, nullable=True)
    items_json = db.Column(db.Text, nullable=True)  # JSON string of cart items (used by place_order)
    shipping_address = db.Column(db.Text, nullable=True)

    # user: provided by User.orders backref
    order_items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")

    @property
    def items(self):
        """Items as list: from OrderItem rows if any, else from items_json. Each item has .product_name, .quantity (and .price)."""
        if self.order_items:
            return list(self.order_items)
        if self.items_json:
            try:
                data = json.loads(self.items_json)
                return [
                    SimpleNamespace(
                        product_name=x.get("name") or x.get("product_name", ""),
                        product_state=x.get("state") or x.get("product_state", ""),
                        quantity=int(x.get("quantity", 1)),
                        price=float(x.get("price", 0)),
                        image=x.get("image") or "",
                    )
                    for x in (data if isinstance(data, list) else [])
                ]
            except Exception:
                return []
        return []


class OrderItem(db.Model):
    """Order line item (used when order is created with order_number + line items)."""
    __tablename__ = "order_items"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    product_state = db.Column(db.String(100), nullable=True)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, nullable=False)
