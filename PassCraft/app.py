from flask import Flask, render_template, request, redirect, session, flash, send_file, after_this_request, send_from_directory, current_app
from reportlab.lib.pagesizes import portrait
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import fonts
from PIL import Image
import pandas as pd
import smtplib
from qrcode import QRCode as QRCodeGenerator
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from io import BytesIO
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import re
import os
import zipfile
import shutil

# Register the fonts
pdfmetrics.registerFont(TTFont('Arial', 'static/fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('Times New Roman', 'static/fonts/times new roman.ttf'))
pdfmetrics.registerFont(TTFont('Courier New', 'static/fonts/cour.ttf'))
pdfmetrics.registerFont(TTFont('Brush Script MT', 'static/fonts/brush script mt kursiv.ttf'))


app = Flask(__name__)
app.secret_key = 'secretkey'
app.config['UPLOAD_FOLDER'] = 'static/downloadables'

ALLOWED_EXTENSIONS_P = {'png'}
ALLOWED_EXTENSIONS_X = {'xlsx'}


def allowed_file_png(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_P

def allowed_file_excel(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_X


@app.route('/', methods=['GET'])
def welcome():
    session.clear()
    clear_static_folder()
    return render_template('welcome.html')


@app.route('/form', methods=['GET', 'POST'])
def form():
    if request.method == 'POST':
        # Process the form submission
        template_file = request.files['template_file']
        spreadsheet_file = request.files['spreadsheet_file']
        
        # Validate file extensions
        if not allowed_file_png(template_file.filename) or not allowed_file_excel(spreadsheet_file.filename):
            flash('Invalid file type. Please upload a PNG template file and an XLSX spreadsheet file.')
            return redirect(request.url)
        
        template_file_path = f"static/uploads/{template_file.filename}"
        spreadsheet_file_path = f"static/uploads/{spreadsheet_file.filename}"
        template_file.save(template_file_path)
        spreadsheet_file.save(spreadsheet_file_path)
        
        session['template_file_path'] = template_file_path
        session['spreadsheet_file_path'] = spreadsheet_file_path
        return redirect('/position')
    
    return render_template('form.html')


@app.route('/position', methods=['GET', 'POST'])
def position():
    template_file_path = session['template_file_path']
    if request.method == 'POST':
        # Process the form submission
        try:
            x_position = int(request.form['x_position'])
            y_position = int(request.form['y_position'])
            font_size = int(request.form['font_size'])
        except ValueError:
            flash('Invalid input. Please enter valid integers for X Position, Y Position, and Font Size.')
            return redirect(request.url)
        
        font_family = request.form['font_family']
        text_color = request.form['text_color']
        
        session['x_position'] = x_position
        session['y_position'] = y_position
        session['font_size'] = font_size
        session['font_family'] = font_family
        session['text_color'] = text_color
        
        return redirect('/qrcode')
    
    return render_template('position.html', template_file_path=template_file_path)

@app.route('/qrcode', methods=['GET', 'POST'])
def qrcode():
    template_file_path = session['template_file_path']
    x_position = session['x_position']
    y_position = session['y_position']
    font_size = session['font_size']
    font_family = session['font_family']
    text_color = session['text_color']
    if request.method == 'POST':
        # Process the form submission
        try:
            x_position = int(request.form['x_position'])
            y_position = int(request.form['y_position'])
            code_size = int(request.form['code_size'])
        except ValueError:
            flash('Invalid input. Please enter valid integers for X Position, Y Position, and Font Size.')
            return redirect(request.url)
        
        next_step = request.form['next_step']
        
        session['code_x_position'] = x_position
        session['code_y_position'] = y_position
        session['code_size'] = code_size
        
        if next_step == "Download Cards":
            return redirect('/downloader')
        
        return redirect("/email")
    
    return render_template('qrcode.html', template_file_path=template_file_path, x_position=x_position, y_position=y_position, 
                           font_size=font_size, font_family=font_family, text_color=text_color)



@app.route('/downloader', methods=['GET', 'POST'])
def downloader():
    return render_template('downloader.html')

@app.route('/download')
def download():
    template_file_path = session['template_file_path']
    spreadsheet = session['spreadsheet_file_path']
    qr_x = session['code_x_position']
    qr_y = session['code_y_position']
    qr_size = session['code_size']
    x_pos = session['x_position']
    y_pos = session['y_position']
    f_size = session['font_size']
    f_fam = session['font_family']
    t_col = session['text_color']
    
        # Generate membership cards and save them locally as a zip file
    path = generate_membership_cards_and_save_locally(template_file_path, spreadsheet, qr_x, qr_y, qr_size,
                                                                         x_pos, y_pos, f_size, f_fam, t_col)
        
        # Return the zip file for download
    # @after_this_request
    # def redirect_to_ending(response):
    #     return redirect('/ending')
    
    return send_file(path, as_attachment=True)


@app.route('/email', methods=['GET', 'POST'])
def email():
    if request.method == 'POST':
        # Process the form submission
        sender_email = request.form['sender_email']
        sender_password = request.form['sender_password']
        email_subject = request.form['email_subject']
        email_greeting = request.form['email_greeting']
        email_body = request.form['email_body']
        
        # Validate sender email
        if not re.match(r"[^@]+@[^@]+\.[^@]+", sender_email):
            flash('Invalid email address. Please enter a valid email address for the sender.')
            return redirect(request.url)
        
        # Validate other input fields
        if not sender_password or not email_subject or not email_greeting or not email_body:
            flash('Please fill in all the email details.')
            return redirect(request.url)
        
        # Retrieve the file paths and positions from the session
        template_file_path = session['template_file_path']
        spreadsheet_file_path = session['spreadsheet_file_path']
        x_position = session['x_position']
        y_position = session['y_position']
        font_size = session['font_size']
        font_family = session['font_family']
        text_color = session['text_color']
        qrcode_x = session['code_x_position']
        qrcode_y = session['code_y_position']
        qrcode_size = session['code_size']
        
        # Generate membership cards and send emails
        generate_membership_cards_and_send_emails(template_file_path, spreadsheet_file_path, qrcode_x, qrcode_y, qrcode_size,
                                                  x_position, y_position, font_size, font_family, text_color,
                                                  sender_email, sender_password, email_subject,
                                                  email_greeting, email_body)
        
        return redirect('/ending')  # Placeholder success message
    
    return render_template('email.html')


@app.route('/ending', methods=['GET'])
def ending():
    return render_template('ending.html')

@app.route('/tutorial', methods=['GET'])
def tutorial():
    return render_template('tutorial.html')

@app.route('/verify/<name>')
def verify(name):
    return render_template('verify.html', member_name= name.replace("-", " "))

def generate_membership_cards_and_save_locally(template_file_path, spreadsheet_file_path, qr_x, qr_y, qr_size, x_pos, y_pos, f_size, f_fam,
                                              t_col):
    df = pd.read_excel(spreadsheet_file_path, sheet_name="Sheet1")
    membership_card_dir = "static/membership_cards"
    
    # Create the directory to store the generated membership cards if it doesn't exist
    os.makedirs(membership_card_dir, exist_ok=True)
    
    for index, row in df.iterrows():
        member_name = row['Name']
        first_name, last_name = member_name.split()  # Split name into first and last name

        output_file = f"{membership_card_dir}/MembershipCard_{member_name}.pdf"
        
        # Get the actual size of the PNG template
        image = Image.open(template_file_path)
        template_width, template_height = image.size

        qr_code_data = f"http://127.0.0.1:5000/verify/{first_name}-{last_name}"
        
        # Step 2: Create the QR code image
        if qr_size > 0:
            qr = QRCodeGenerator(version=1, box_size=10, border=5)
            qr.add_data(qr_code_data)
            qr.make(fit=True)

            qr_image = qr.make_image(fill_color="black", back_color="white")
        
        c = canvas.Canvas(output_file, pagesize=(template_width, template_height))
        c.drawImage(ImageReader(image), 0, 0, width=template_width, height=template_height)

        if qr_size > 0:
            qr_image_path = f"static/qrcodes/{member_name}_qr.png"
            qr_image.save(qr_image_path)
            c.drawImage(qr_image_path, qr_x, qr_y, width=qr_size, height=qr_size)
        
        c.setFont(f_fam, f_size)
        c.setFillColor(t_col)
        name_x = x_pos  # Center X position
        name_y = y_pos  # Center Y position
        c.drawString(name_x, name_y, member_name)
        
        c.save()
        print(f"Generated card for {member_name} -> {output_file}")
        
    # Zip all the card files into a single zip file
    zip_file_path = f"{membership_card_dir}/cards.zip"
    with zipfile.ZipFile(zip_file_path, 'w') as zipf:
        for card_file in os.listdir(membership_card_dir):
            if card_file.endswith(".pdf"):
                zipf.write(os.path.join(membership_card_dir, card_file), card_file)

    return zip_file_path  # Return the directory where the membership cards are stored


def generate_membership_cards_and_send_emails(template_file_path, spreadsheet_file_path, qr_x, qr_y, qr_size, x_pos, y_pos, f_size, f_fam,
                                              t_col, sender_email, sender_password, email_subject, email_greeting,
                                              email_body):
    df = pd.read_excel(spreadsheet_file_path, sheet_name="Sheet1")
    
    for index, row in df.iterrows():
        member_name = row['Name']
        first_name, last_name = member_name.split()  # Split name into first and last name
        member_email = row['Email']  # Get member's email from the spreadsheet
        
        output_file = f"static/membership_cards/MembershipCard_{member_name}.pdf"
        
        # Get the actual size of the PNG template
        image = Image.open(template_file_path)
        template_width, template_height = image.size

        qr_code_data = f"http://127.0.0.1:5000/verify/{first_name}-{last_name}"
        
        # Step 2: Create the QR code image
        if qr_size > 0:
            qr = QRCodeGenerator(version=1, box_size=10, border=5)
            qr.add_data(qr_code_data)
            qr.make(fit=True)

            qr_image = qr.make_image(fill_color="black", back_color="white")
        
        c = canvas.Canvas(output_file, pagesize=(template_width, template_height))
        c.drawImage(ImageReader(image), 0, 0, width=template_width, height=template_height)

        if qr_size > 0:
            qr_image_path = f"static/qrcodes/{member_name}_qr.png"
            qr_image.save(qr_image_path)
            c.drawImage(qr_image_path, qr_x, qr_y, width=qr_size, height=qr_size)
        
        c.setFont(f_fam, f_size)
        c.setFillColor(t_col)
        name_x = x_pos  # Center X position
        name_y = y_pos  # Center Y position
        c.drawString(name_x, name_y, member_name)
        
        c.save()
        print(f"Generated card for {member_name} -> {output_file}")
        
        # Send email with the generated PDF attachment
        send_email(sender_email, sender_password, member_email, member_name, email_subject, email_greeting,
                   email_body, output_file)


def send_email(s_email, s_pass, recipient_email, recipient_name, email_subject, email_greeting, email_body,
               attachment_file):
    # Email configuration
    sender_email = s_email  # Replace with your email address
    sender_password = s_pass  # Replace with your email password

    # Create a multipart message
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = recipient_email
    message["Subject"] = email_subject

    # Add body text to the email
    body = f"{email_greeting} {recipient_name},\n\n{email_body}"
    message.attach(MIMEText(body, "plain"))

    # Open the PDF file in binary mode
    with open(attachment_file, "rb") as attachment:
        # Add PDF attachment to the email
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())

    # Encode the attachment and add headers
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename= {attachment_file}")
    message.attach(part)

    # Connect to the SMTP server and send the email
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, message.as_string())
        print(f"Email sent to {recipient_email}")


def clear_static_folder():
    # Get the path to the 'static' folder
    static_folder = os.path.join(os.getcwd(), 'static')

    # Clear all files within the 'static' folder except styles.css, qrcodesample.png, and files in static/fonts folder
    for root, dirs, files in os.walk(static_folder):
        # Skip deletion for the 'static/fonts' directory and its contents
        if root.endswith('fonts'):
            continue
        
        for file in files:
            if file != 'styles.css' and file != 'qrcodesample.png':
                file_path = os.path.join(root, file)
                os.remove(file_path)




if __name__ == '__main__':
    app.run(debug=True)
