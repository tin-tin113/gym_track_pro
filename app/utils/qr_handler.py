"""QR Code generation and validation utilities."""

import qrcode
from io import BytesIO
import base64
from datetime import datetime, timedelta
import uuid
from app import db
from app.models.attendance import Attendance


def generate_qr_code(member_id, expiry_hours=24):
    """
    Generate a QR code for member check-in with unique session token.

    Args:
        member_id: ID of the member
        expiry_hours: Hours until QR token expires (default 24)

    Returns:
        Dictionary with:
        - qr_image_base64: Base64-encoded PNG image
        - session_token: Unique token for validation
        - expiry_time: Expiry datetime
        - qr_url: URL-encoded token value
    """
    try:
        # Generate unique session token
        session_token = str(uuid.uuid4())
        expiry_time = datetime.utcnow() + timedelta(hours=expiry_hours)

        # Create QR code data - simple format: MEMBER_ID:TOKEN:TIMESTAMP
        qr_data = f"GYMTRACK:{member_id}:{session_token}:{int(expiry_time.timestamp())}"

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()

        return {
            'qr_image_base64': img_str,
            'session_token': session_token,
            'expiry_time': expiry_time,
            'qr_url': qr_data,
            'success': True,
            'error': None
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Error generating QR code: {str(e)}',
            'qr_image_base64': None,
            'session_token': None,
            'expiry_time': None
        }


def get_qr_image_base64(member_id):
    """
    Get QR code as base64 PNG for display in HTML.

    Args:
        member_id: ID of the member

    Returns:
        Base64 encoded PNG or error dict
    """
    result = generate_qr_code(member_id)
    if result['success']:
        return f"data:image/png;base64,{result['qr_image_base64']}"
    return None


def validate_qr_token(token):
    """
    Validate QR code token and extract member ID.

    Args:
        token: QR token string from scanned code

    Returns:
        Dictionary with:
        - is_valid: Boolean validity
        - member_id: Extracted member ID
        - expired: Whether token has expired
        - error: Error message if invalid
    """
    try:
        # Parse QR data: GYMTRACK:MEMBER_ID:SESSION_TOKEN:TIMESTAMP
        if not token.startswith('GYMTRACK:'):
            return {
                'is_valid': False,
                'member_id': None,
                'expired': False,
                'error': 'Invalid QR format'
            }

        parts = token.split(':')
        if len(parts) != 4:
            return {
                'is_valid': False,
                'member_id': None,
                'expired': False,
                'error': 'Invalid QR format'
            }

        prefix, member_id_str, session_token, timestamp_str = parts

        try:
            member_id = int(member_id_str)
            expiry_timestamp = int(timestamp_str)
        except ValueError:
            return {
                'is_valid': False,
                'member_id': None,
                'expired': False,
                'error': 'Invalid QR data format'
            }

        # Check expiry
        now_timestamp = int(datetime.utcnow().timestamp())
        if now_timestamp > expiry_timestamp:
            return {
                'is_valid': False,
                'member_id': member_id,
                'expired': True,
                'error': 'QR code has expired'
            }

        # Verify token exists in database (optional, for security)
        attendance = Attendance.query.filter_by(qr_code=session_token).first()
        if attendance:
            return {
                'is_valid': False,
                'member_id': member_id,
                'expired': False,
                'error': 'QR code already used'
            }

        return {
            'is_valid': True,
            'member_id': member_id,
            'session_token': session_token,
            'expired': False,
            'error': None
        }

    except Exception as e:
        return {
            'is_valid': False,
            'member_id': None,
            'expired': False,
            'error': f'Error validating token: {str(e)}'
        }


def get_qr_expiry_countdown(expiry_time):
    """
    Get human-readable countdown to QR expiry.

    Args:
        expiry_time: Datetime object of expiry

    Returns:
        Dictionary with minutes and seconds remaining
    """
    now = datetime.utcnow()
    if expiry_time <= now:
        return {'minutes': 0, 'seconds': 0, 'expired': True}

    delta = expiry_time - now
    total_seconds = int(delta.total_seconds())
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    return {
        'minutes': minutes,
        'seconds': seconds,
        'expired': False,
        'total_seconds': total_seconds
    }
