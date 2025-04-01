import imaplib
import email
from email.header import decode_header
import os
import asyncio
import csv
import datetime
import shutil
import re
from pydub import AudioSegment
import speech_recognition as sr
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from loguru import logger
from dotenv import load_dotenv
from email_agent.send_mail import process_customer_complaint, clean_email_body, process_email_sending
from email_agent.crm import insert_partial_customer_query

load_dotenv()

# Email credentials & IMAP config
EMAIL = os.getenv('USERNAME_EMAIL')
PASSWORD = os.getenv('MAIL_PASSWORD')
IMAP_SERVER = os.getenv('IMAP')
IMAP_PORT = 993

# Track the latest email ID we've processed
last_processed_id = 0

# Define the directory to save downloaded files
DOWNLOAD_DIR = "email_attachments"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
    logger.info(f"Created download directory: {DOWNLOAD_DIR}")

# CSV file to track downloads
CSV_FILE = "email_downloads.csv"
CSV_HEADERS = ["timestamp", "sender", "subject", "filename", "file_path"]

# List of supported audio/video file extensions
SUPPORTED_EXTENSIONS = [
    # Video formats
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp',
    # Audio formats
    '.mp3', '.wav', '.aac', '.ogg', '.flac', '.m4a', '.wma'
]

# Flag to track if we're currently processing files
is_processing = False

# Standard response messages
SHORT_TEXT_RESPONSE = {
    "subject": "Additional Information Required",
    "body": "Thank you for contacting us. Your query appears to be too brief for us to understand your specific needs. Please send us a more detailed description of your issue or question (at least 30 words) so we can assist you properly."
}

SHORT_AUDIO_RESPONSE = {
    "subject": "Additional Information Required",
    "body": "Thank you for your audio message. Unfortunately, the recording is too short for us to properly understand your query. Please send a longer audio recording (at least 5 seconds) or provide your query in text format with sufficient details."
}

def initialize_csv():
    """Initialize the CSV file if it doesn't exist"""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_HEADERS)
            writer.writeheader()
            logger.info(f"Created CSV tracking file: {CSV_FILE}")

async def clear_directory():
    """Completely empties the download directory."""
    try:
        logger.info(f"Clearing directory: {DOWNLOAD_DIR}")
        for filename in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                logger.info(f"Deleted file during cleanup: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting {file_path}: {e}")
    except Exception as e:
        logger.error(f"Error clearing directory: {e}")

def log_download_to_csv(sender, subject, filename, file_path):
    """Log download information to CSV file"""
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_HEADERS)
        writer.writerow({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sender": sender,
            "subject": subject,
            "filename": filename,
            "file_path": file_path
        })
    logger.info(f"Logged download info to CSV: {filename}")

async def convert_mp3_to_wav(file_path):
    """Converts MP3 to WAV and returns the new file path."""
    wav_path = file_path.replace(".mp3", ".wav")  # Change extension
    try:
        audio = AudioSegment.from_mp3(file_path)
        audio.export(wav_path, format="wav")  # Convert to WAV
        logger.info(f"Converted {file_path} to {wav_path}")
        # Delete the original MP3 file after conversion
        os.remove(file_path)
        logger.info(f"Deleted original MP3 file: {file_path}")
        return wav_path
    except Exception as e:
        logger.error(f"Failed to convert {file_path} to WAV: {e}")
        return None

async def process_audio(file_path):
    """Processes the audio file and converts speech to text. Returns None if audio is too short."""
    recognizer = sr.Recognizer()
    
    # Convert MP3 to WAV if necessary
    if file_path.endswith(".mp3"):
        file_path = await convert_mp3_to_wav(file_path)
        if file_path is None:
            return None  # Skip if conversion failed

    try:
        # First check the duration of the audio file
        audio = AudioSegment.from_file(file_path)
        duration_seconds = len(audio) / 1000  # Convert from ms to seconds
        
        # Check if audio is too short
        if duration_seconds < 5:
            logger.warning(f"Audio file {file_path} is too short: {duration_seconds:.2f} seconds (minimum 5s required)")
            # Delete the file after checking
            os.remove(file_path)
            logger.info(f"Deleted short audio file: {file_path}")
            return "TOO_SHORT"  # Special return value to indicate too short audio
        
        # Process audio of acceptable length
        with sr.AudioFile(file_path) as source:
            logger.info(f"Processing file: {file_path}")
            audio_data = recognizer.record(source)
        
        text = recognizer.recognize_google(audio_data)
        print(f"\n🔊 Transcribed Text from {os.path.basename(file_path)}:\n{text}\n")
        logger.info(f"Transcription successful: {text}")

        # Delete the file after processing
        os.remove(file_path)
        logger.info(f"Deleted processed file: {file_path}")
        return text

    except sr.UnknownValueError:
        logger.error(f"Could not understand the audio: {file_path}")
        # Still delete the file even if transcription failed
        os.remove(file_path)
        logger.info(f"Deleted unrecognizable audio file: {file_path}")
    except sr.RequestError:
        logger.error("Error connecting to speech recognition service.")
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        # Try to delete the file even if an error occurred
        try:
            os.remove(file_path)
            logger.info(f"Deleted file after error: {file_path}")
        except:
            pass
    return None

async def process_existing_files():
    """Processes any audio files present in the folder."""
    global is_processing
    
    if is_processing:
        logger.info("Already processing files, skipping...")
        return []  # Skip if already processing files
    
    is_processing = True
    transcriptions = []
    short_files = []
    
    try:
        # Get list of all audio files in the directory
        audio_files = []
        for filename in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(file_path) and file_path.lower().endswith(('.wav', '.mp3', '.flac', '.ogg')):
                audio_files.append(file_path)
        
        if audio_files:
            logger.info(f"Found {len(audio_files)} audio files to process")
            
            # Process each file
            for file_path in audio_files:
                logger.info(f"Processing file: {file_path}")
                text = await process_audio(file_path)
                
                if text == "TOO_SHORT":
                    # Audio was too short, add to short files list
                    short_files.append(os.path.basename(file_path))
                elif text:
                    # Valid transcription
                    transcriptions.append((os.path.basename(file_path), text))
    except Exception as e:
        logger.error(f"Error in batch processing: {e}")
    finally:
        is_processing = False
        return transcriptions, short_files

def extract_name_from_sender(from_string):
    """Extract name from the sender email string."""
    name_match = re.search(r'^(.*?)\s<', from_string)
    if name_match:
        return name_match.group(1)
    name_match = re.search(r'"(.*?)"', from_string)
    if name_match:
        return name_match.group(1)
    return "Customer"

def extract_email_from_sender(from_string):
    """Extract email address from the sender string."""
    email_match = re.search(r'<(.*?)>', from_string)
    if email_match:
        return email_match.group(1)
    return from_string

async def monitor_new_emails():
    global last_processed_id
    
    # Initialize CSV file
    initialize_csv()
    
    logger.info("🚀 Email monitoring started...")
    
    while True:
        try:
            logger.info(f"Connecting to IMAP server {IMAP_SERVER} with user {EMAIL}...")
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mail.login(EMAIL, PASSWORD)
            logger.info("Successfully logged in to IMAP server.")
            
            mail.select("inbox")
            status, count_data = mail.status('INBOX', '(MESSAGES)')
            if status != "OK":
                logger.warning("Failed to get inbox status.")
                continue
                
            messages_count = int(count_data[0].decode().split()[2].strip(').,]'))
            logger.info(f"Total emails in inbox: {messages_count}")
            
            # If this is the first run, just record the latest email ID
            if last_processed_id == 0 and messages_count > 0:
                last_processed_id = messages_count
                logger.info(f"First run: Setting last processed ID to {last_processed_id}")
                mail.logout()
                await asyncio.sleep(5)
                continue
            
            # Check if there are new emails
            if messages_count > last_processed_id:
                new_emails_count = messages_count - last_processed_id
                logger.info(f"Found {new_emails_count} new email(s)!")
                
                has_new_media = False
                downloaded_files_info = []
                
                # Fetch only the new emails
                for i in range(last_processed_id + 1, messages_count + 1):
                    logger.info(f"Fetching new email ID: {i}")
                    res, msg_data = mail.fetch(str(i), "(RFC822)")
                    if res != "OK":
                        logger.error(f"Error fetching email ID {i}")
                        continue
                    
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    # Extract subject
                    subject, encoding = decode_header(msg.get("Subject", "No Subject"))[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    
                    # Extract sender email
                    from_ = msg.get("From", "Unknown")
                    
                    # Extract email body and check for attachments
                    body = "No Content"
                    email_downloaded_files = []
                    
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            
                            # Get the text content
                            if "attachment" not in content_disposition and content_type == "text/plain":
                                body = part.get_payload(decode=True).decode(errors="ignore")
                            
                            # Download audio/video attachments
                            if "attachment" in content_disposition:
                                try:
                                    filename = part.get_filename()
                                    if filename:
                                        # Decode filename if needed
                                        if isinstance(filename, bytes):
                                            filename = filename.decode()
                                        elif decode_header(filename)[0][1] is not None:
                                            filename = decode_header(filename)[0][0]
                                            if isinstance(filename, bytes):
                                                filename = filename.decode(decode_header(filename)[0][1])
                                        
                                        # Check if the file is an audio or video file
                                        file_ext = os.path.splitext(filename)[1].lower()
                                        if file_ext in SUPPORTED_EXTENSIONS:
                                            # Found media file, clear previous files if this is the first one
                                            if not has_new_media:
                                                await clear_directory()
                                                has_new_media = True
                                            
                                            # Sanitize filename to avoid issues
                                            filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
                                            
                                            filepath = os.path.join(DOWNLOAD_DIR, filename)
                                            with open(filepath, 'wb') as f:
                                                f.write(part.get_payload(decode=True))
                                            
                                            abs_path = os.path.abspath(filepath)
                                            email_downloaded_files.append((filename, abs_path))
                                            
                                            # Add to our tracking list
                                            downloaded_files_info.append({
                                                "sender": from_,
                                                "subject": subject,
                                                "filename": filename,
                                                "file_path": abs_path
                                            })
                                            
                                            logger.info(f"Downloaded: {abs_path}")
                                except Exception as e:
                                    logger.error(f"Error downloading attachment: {e}")
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")
                    
                    # Return the new email details
                    logger.info(f"📩 New email received: \nFrom: {from_} \nSubject: {subject}\nBody: {body[:200]}...\n")
                    
                    # Process email based on content
                    # Count words in the body for decision making
                    word_count = len(body.strip().split()) if body and body.strip() else 0
                    
                    # Extract name and email for processing
                    name = extract_name_from_sender(from_)
                    recipient_email = extract_email_from_sender(from_)
                    
                    # Decision logic for text vs audio processing
                    if has_new_media and word_count < 20:
                        # Short text with attachments - prioritize audio processing
                        # This will be handled later in the audio processing section
                        logger.info(f"Email contains audio attachments and short text ({word_count} words). Will process audio.")
                    else:
                        # Process text directly
                        if word_count > 0:
                            # Check if text is too short (less than 30 words)
                            if word_count < 30:
                                logger.info(f"Text is too short ({word_count} words). Sending request for more details.")
                                try:
                                    # Record partial customer data
                                    insert_partial_customer_query(from_)
                                    
                                    # Send response asking for more details
                                    clean_body = clean_email_body(SHORT_TEXT_RESPONSE["body"])
                                    logger.info(f"Sending short text response to: {recipient_email}")
                                    email_result = process_email_sending(
                                        SHORT_TEXT_RESPONSE["subject"], 
                                        clean_body, 
                                        recipient_email
                                    )
                                    logger.info(f"Short text response email result: {email_result}")
                                except Exception as e:
                                    logger.error(f"Error sending short text response: {e}")
                            else:
                                # Process adequate length text
                                logger.info(f"Processing email body text directly. Word count: {word_count}")
                                try:
                                    # Record partial customer data
                                    insert_partial_customer_query(from_)
                                    
                                    # Process the text content
                                    response = process_customer_complaint(body, name)
                                    
                                    # Extract subject and body from response
                                    if isinstance(response, dict):
                                        response_subject = response.get("subject", "Customer Support")
                                        response_body = response.get("body", "No response generated")
                                    else:
                                        # Handle case where response might be a string or other object
                                        response_subject = "Customer Support"
                                        response_body = str(response)
                                    
                                    # Clean up and send email response
                                    clean_body = clean_email_body(response_body)
                                    logger.info(f"Sending email response to: {recipient_email}")
                                    email_result = process_email_sending(response_subject, clean_body, recipient_email)
                                    logger.info(f"Email sent result: {email_result}")
                                except Exception as e:
                                    logger.error(f"Error processing text content: {e}")
                    
                    # Log downloaded files for this email
                    if email_downloaded_files:
                        logger.info(f"Downloaded {len(email_downloaded_files)} audio/video files from this email:")
                        for filename, file_path in email_downloaded_files:
                            logger.info(f"📁 File saved at: {file_path}")
                    else:
                        logger.info("No audio/video attachments found in this email.")
                
                # Log all downloads to CSV
                for file_info in downloaded_files_info:
                    filtered_email = file_info['sender']
                    email_data = extract_email_from_sender(filtered_email)
                    log_download_to_csv(
                        filtered_email,
                        file_info["subject"],
                        file_info["filename"],
                        file_info["file_path"]
                    )

                # If we found and downloaded new media, process it immediately
                if has_new_media:
                    logger.info("Processing newly downloaded audio files...")
                    transcriptions, short_files = await process_existing_files()
                    
                    # Handle short audio files
                    if short_files:
                        logger.info(f"Found {len(short_files)} audio files that were too short")
                        # Get unique senders for short audio files
                        short_audio_senders = set()
                        for filename in short_files:
                            file_info = next((info for info in downloaded_files_info if info["filename"] == filename), None)
                            if file_info:
                                sender_email = extract_email_from_sender(file_info['sender'])
                                short_audio_senders.add(sender_email)
                        
                        # Send responses for short audio files
                        for sender_email in short_audio_senders:
                            logger.info(f"Sending short audio response to: {sender_email}")
                            try:
                                clean_body = clean_email_body(SHORT_AUDIO_RESPONSE["body"])
                                email_result = process_email_sending(
                                    SHORT_AUDIO_RESPONSE["subject"], 
                                    clean_body, 
                                    sender_email
                                )
                                logger.info(f"Short audio response email result: {email_result}")
                            except Exception as e:
                                logger.error(f"Error sending short audio response: {e}")
                    
                    # Handle valid transcriptions
                    if transcriptions:
                        logger.info(f"Successfully transcribed {len(transcriptions)} audio files:")
                        for filename, text in transcriptions:
                            # Find the corresponding file info to get the sender
                            file_info = next((info for info in downloaded_files_info if info["filename"] == filename), None)
                            if file_info:
                                sender_name = extract_name_from_sender(file_info['sender'])
                                recipient_email = extract_email_from_sender(file_info['sender'])
                            else:
                                sender_name = "Customer"
                                recipient_email = "unknown@example.com"
                                logger.warning(f"Could not find sender info for {filename}")
                            
                            # Process the transcribed text
                            response = process_customer_complaint(text, sender_name)
                            
                            # Extract subject and body
                            if isinstance(response, dict):
                                subject = response.get("subject", "Customer Support")
                                body = response.get("body", "No response generated")
                            else:
                                # Handle case where response might be a string or other object
                                subject = "Customer Support"
                                body = str(response)
                            
                            # Clean up and send the email
                            clean_body = clean_email_body(body)
                            logger.info(f"Sending email response for audio transcription to: {recipient_email}")
                            email_result = process_email_sending(subject, clean_body, recipient_email)
                            logger.info(f"Email sent result: {email_result}")
                    else:
                        logger.info("No successful transcriptions from the downloaded files.")
            
                # Update the last processed ID
                last_processed_id = messages_count
            else:
                logger.info("No new emails.")
            
            mail.logout()
            logger.info("Logged out from IMAP server.")
        
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP authentication error: {e}")
        except Exception as e:
            logger.error(f"General error monitoring emails: {e}")
        
        logger.info("Waiting for new emails...")
        await asyncio.sleep(5)

async def main():
    # Start with a clean directory
    await clear_directory()
    
    # Start monitoring emails
    await monitor_new_emails()

if __name__ == "__main__":
    asyncio.run(main())