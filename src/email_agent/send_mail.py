import os
import json
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI
from crewai import Agent, Task, Crew
from loguru import logger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)



complaint_analyzer = Agent(
    role="Complaint Analyzer",
    goal="Accurately extract and categorize customer complaints",
    backstory="""You are an expert in customer service with a background in natural language processing. 
    Your specialty is understanding customer needs and extracting key information from their messages.
    You need to extract only customer names (from username not from text), product issues, address, order IDs, and refund request status from complaint messages.
    """,
    verbose=True,
)

response_generator = Agent(
    role="Response Generator",
    goal="Generate polite and professional customer support responses",
    backstory="Customer service expert with strong empathy and problem-solving skills.",
    verbose=True,
    allow_delegation=False,
)

json_formatter = Agent(
    role="JSON Formatter",
    goal="Format customer service responses into JSON with subject and body fields",
    backstory="""You are a technical specialist who formats text responses into structured JSON objects.
    You take customer service responses and extract an appropriate subject line based on the content,
    then return a JSON object with 'subject' and 'body' fields.""",
    verbose=True,
    allow_delegation=False,
)

def process_customer_complaint(user_message: str,username:str):
    analysis_task = Task(
        description=f"Analyze customer message and extract structured details: '{user_message}' and {username}",
        agent=complaint_analyzer,
        expected_output="A JSON object with complaint details",
    )
    
    customer_service_crew = Crew(
        agents=[complaint_analyzer],
        tasks=[analysis_task],
        verbose=True,
    )
    result = customer_service_crew.kickoff()
    if isinstance(result, dict) and "error" in result:
        logger.error("Error extracting complaint details.")
        return {"error": "Failed to process complaint."}
    
    # Generate Response
    response_task = Task(
        description=f"Generate a polite response based on extracted details: {result}",
        agent=response_generator,
        expected_output="A polite, empathetic mail response with proper subject(subject should be always related to user query) and add in Best regards,supports@.com Customer Service Team 24*7 supports or call us 1-800-123-4567",
    )
    response_crew = Crew(
        agents=[response_generator],
        tasks=[response_task],
        verbose=True,
    )
    response = response_crew.kickoff()
    
    # Format as JSON
    format_task = Task(
        description=f"Format the following response into a JSON object with 'subject' and 'body' fields. Return ONLY the JSON object and nothing else: '{response}'",
        agent=json_formatter,
        expected_output="""A clean JSON object with format: 
        {
            "subject": "Appropriate subject line based on the complaint",
            "body": "The full text of the response"
        }""",
    )
    
    format_crew = Crew(
        agents=[json_formatter],
        tasks=[format_task],
        verbose=True,
    )
    
    formatted_response = format_crew.kickoff()
    
    # Parse the JSON object if it's a string
    if isinstance(formatted_response, str):
        try:
            if '{' in formatted_response and '}' in formatted_response:
                # Extract JSON from string if it might be embedded in text
                start_idx = formatted_response.find('{')
                end_idx = formatted_response.rfind('}') + 1
                json_str = formatted_response[start_idx:end_idx]
                parsed_response = json.loads(json_str)
                
                # IMPORTANT: Extract the actual subject and body from the nested JSON
                if 'body' in parsed_response and isinstance(parsed_response['body'], str):
                    try:
                        # The body might contain another JSON object
                        if parsed_response['body'].strip().startswith('{') and parsed_response['body'].strip().endswith('}'):
                            nested_json = json.loads(parsed_response['body'])
                            if 'subject' in nested_json and 'body' in nested_json:
                                return {
                                    "subject": nested_json['subject'],
                                    "body": nested_json['body']
                                }
                    except:
                        pass
                        
                return parsed_response
            else:
                # Return default structure with original response
                return {"subject": "Customer Support", "body": formatted_response}
        except json.JSONDecodeError:
            # If parsing fails, return the original response
            return {"subject": "Customer Support", "body": formatted_response}
    
    # If formatted_response is already a dictionary or another object
    return {"subject": "Customer Support", "body": str(formatted_response)}

def clean_email_body(body):
    """
    Clean up the email body by:
    1. Converting escaped newlines (\n) to actual newlines
    2. Removing unnecessary quotes
    3. Cleaning up any JSON or formatting artifacts
    
    Args:
        body (str): Raw email body text
        
    Returns:
        str: Cleaned email body text
    """
    # If body is not a string, convert it
    if not isinstance(body, str):
        body = str(body)
    
    # Try to detect if this is a JSON string and extract just the body content
    try:
        if body.strip().startswith('{') and body.strip().endswith('}'):
            parsed = json.loads(body)
            if 'body' in parsed:
                body = parsed['body']
    except:
        pass
        
    # Replace escaped newlines with actual newlines
    body = body.replace('\\n', '\n')
    
    # Replace Unicode escape sequences
    try:
        body = body.encode().decode('unicode_escape')
    except:
        pass
    
    # Remove extra quotes at the beginning and end if they exist
    body = body.strip('"\'')
    
    # Clean up any JSON formatting artifacts
    body = re.sub(r'^\s*"\s*|\s*"\s*$', '', body)
    
    # Replace double backslashes with single backslashes
    body = body.replace('\\\\', '\\')
    
    return body

def process_email_sending(subject, body, recipient):
    """
    Send an email with the given subject and body to the recipient.
    
    Args:
        subject (str): Email subject line
        body (str): Email body content
        recipient (str): Recipient email address
        
    Returns:
        dict: Status of the email sending operation
    """
    # Clean the subject and body
    if not isinstance(subject, str):
        subject = str(subject)
    
    # Remove quotes and extra whitespace from subject
    subject = subject.strip('"\'').strip()
    
    # Clean the body text
    clean_body = clean_email_body(body)
    
    try:
        # Email configuration
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_username = os.getenv("USERNAME_EMAIL")
        smtp_password = os.getenv("MAIL_PASSWORD")
        sender_email = recipient
        
        # Create message
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = recipient
        message["Subject"] = subject
        
        # Attach body with proper newlines preserved
        message.attach(MIMEText(clean_body, "plain"))
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(message)
            
        logger.info(f"Email sent successfully to {recipient}")
        return {
            "status": "success",
            "message": f"Email sent successfully to {recipient}",
            "subject": subject,
            "body_preview": clean_body[:100] + "..." if len(clean_body) > 100 else clean_body
        }
    
    except Exception as e:
        error_msg = f"Failed to send email: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "error",
            "message": error_msg,
            "subject": subject
        }


