from flask import Flask, render_template, request, redirect, url_for,send_file
from flask_sqlalchemy import SQLAlchemy
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from datetime import datetime
from flask import flash
import os
import uuid
app = Flask(__name__)
# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trains.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
db = SQLAlchemy(app)
# Train model for SQLite database
class Train(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    train_id = db.Column(db.String(10), nullable=False)
    from_station = db.Column(db.String(100), nullable=False)
    to_station = db.Column(db.String(100), nullable=False)
    departure = db.Column(db.String(100), nullable=False)
    available_seats = db.Column(db.Integer, nullable=False)
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(36), default=str(uuid.uuid4()), unique=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    from_station = db.Column(db.String(100), nullable=False)
    to_station = db.Column(db.String(100), nullable=False)
    journey_date = db.Column(db.String(100), nullable=False)
    seats = db.Column(db.Integer, nullable=False)
    train_id = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='Booked')  # For Cancel or Refund
def init_db():
    if not os.path.exists('trains.db'):
        with app.app_context():
            db.create_all()
            print("✅ Database created!")            
            # Add this to import train data from CSV
            import csv
            with open('trains.csv') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    train = Train(
                        train_id=row['train_id'],
                        from_station=row['from_station'],
                        to_station=row['to_station'],
                        departure=row['departure'],
                        available_seats=int(row['available_seats'])
                    )
                    db.session.add(train)
                db.session.commit()
            print("🚆 Train data imported!")
@app.route('/')
def index():
    return render_template('index.html')
@app.route('/search_train', methods=['GET', 'POST'])
def search_train():
    if request.method == 'POST':
        from_station = request.form['from'].strip().title()
        to_station = request.form['to'].strip().title()
        journey_date = request.form['journeyDate']        
        try:
            formatted_date = datetime.strptime(journey_date, '%Y-%m-%d').strftime('%d-%m-%Y')
            available_trains = Train.query.filter(
                Train.from_station.ilike(f'%{from_station}%'),
                Train.to_station.ilike(f'%{to_station}%'),
                Train.departure.like(f'%{formatted_date}%')
            ).all()
            
            return render_template('schedule.html', trains=available_trains)            
        except Exception as e:
            flash('Error processing your search', 'error')
            return redirect(url_for('search_train'))    
    return render_template('search_train.html') 
@app.route('/book', methods=['GET', 'POST'])
def book():
    if request.method == 'POST':
        train_id = request.form['train_id']
        seats_needed = int(request.form['seats'])        
        # Check seat availability
        train = Train.query.filter_by(train_id=train_id).first()
        if not train or train.available_seats < seats_needed:
            flash('Not enough seats available', 'error')
            return redirect(url_for('search_train'))        
        # Proceed with booking
        booking_data = {
            'name': request.form['name'],
            'email': request.form['email'],
            'phone': request.form['phone'],
            'from_station': request.form['from'],
            'to_station': request.form['to'],
            'journey_date': request.form['journeyDate'],
            'seats': seats_needed,
            'train_id': train_id
        }
        # Update available seats
        train.available_seats -= seats_needed    
        # Save to database
        booking = Booking(**booking_data)
        db.session.add(booking)
        db.session.commit()        
        return render_template('confirmation.html', 
                            booking_id=booking.booking_id,
                            **booking_data)
    return render_template('book.html')
@app.route('/cancel', methods=['GET', 'POST'])
def cancel():
    if request.method == 'POST':
        booking_id = request.form['booking_id']
        booking = Booking.query.filter_by(booking_id=booking_id).first()        
        if booking:
            booking.status = 'Cancelled'
            db.session.commit()
            return render_template('cancel.html', message="Ticket Cancelled Successfully.")
        else:
            return render_template('cancel.html', message="Booking ID not found.")
    return render_template('cancel.html')
@app.route('/refund', methods=['GET', 'POST'])
def refund():
    if request.method == 'POST':
        booking_id = request.form['booking_id']
        booking = Booking.query.filter_by(booking_id=booking_id).first()
        if booking:
            booking.status = 'Refunded'
            db.session.commit()
            return render_template('refund.html', message="Refund Processed Successfully.")
        else:
            return render_template('refund.html', message="Booking ID not found.")
    return render_template('refund.html')
@app.route('/statement/<booking_id>')
def statement(booking_id):
    booking = Booking.query.filter_by(id=booking_id).first()
    return render_template('statement.html', booking=booking)
@app.route('/booking-stats')
def booking_stats():
    # Example: Count of bookings by date
    data = db.session.query(Booking.date, db.func.count(Booking.id)).group_by(Booking.date).all()
    dates = [d[0].strftime('%Y-%m-%d') for d in data]
    counts = [d[1] for d in data]
    return render_template('booking_chart.html', dates=dates, counts=counts)
@app.route('/print_ticket/<booking_id>')
def print_ticket(booking_id):
    booking = Booking.query.filter_by(booking_id=booking_id).first()
    if booking:
        return render_template('print_ticket.html', booking=booking)
    else:
        flash('Booking ID not found.', 'error')
        return redirect(url_for('cancel')) # Or some other appropriate page
@app.route('/download_ticket/<booking_id>')
def download_ticket(booking_id):
    booking = Booking.query.filter_by(booking_id=booking_id).first()
    if not booking:
        flash('Booking ID not found for download.', 'error')
        return redirect(url_for('cancel')) # Or some other appropriate page
    # Generate PDF content
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    textobject = p.beginText(inch, 10.5 * inch)
    textobject.setFont("Helvetica-Bold", 16)
    textobject.textLine("Railway Ticket")
    textobject.setFont("Helvetica", 12)
    textobject.textLine(f"Booking ID: {booking.booking_id}")
    textobject.textLine(f"Train ID: {booking.train_id}")
    textobject.textLine(f"From: {booking.from_station} to {booking.to_station}")
    textobject.textLine(f"Journey Date: {booking.journey_date}")
    textobject.textLine(f"Passenger Name: {booking.name}")
    textobject.textLine(f"Number of Seats: {booking.seats}")
    p.drawText(textobject)
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"ticket_{booking.booking_id}.pdf", mimetype='application/pdf')
if __name__ == "__main__":
    init_db()
    print("🚀 Starting Flask App...")
    app.run(debug=True)
