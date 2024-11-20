import sys
import os
#from connection_manager import send_request  # Import the connection utility

# Add the current directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'protos'))






import grpc
from protos import lms_pb2
from protos import lms_pb2_grpc
import threading

def view_logs(stub, token):
    """Retrieve and display log entries from the server."""
    response = stub.get_logs(lms_pb2.LogRequest(token=token))
    if response.status == "success":
        print("Log entries on the current server:")
        for log in response.logs:
            print(f"Index: {log.index}, Command: {log.command}, Term: {log.term}")
    else:
        print("Failed to retrieve logs.")

def student_menu(stub):
    while True:
        print("\nStudent Menu:")
        print("1. Register")
        print("2. Login")
        print("3. Upload Assignment")
        print("4. View Course Materials")
        print("5. View Grades")
        print("6. Ask Question")
        print("7. See feedback from instructor") 
        print("8. View Server Logs")   # New Option
        print("9. Logout")
        print("10. Exit")

        choice = input("Select an option: ")

        if choice == "1":
            username = input("Enter username: ")
            password = input("Enter password: ")
            role = "student"
            register_response = stub.register(lms_pb2.RegisterRequest(username=username, password=password, role=role))
            print(register_response.status)

        elif choice == "2":
            username = input("Enter username: ")
            password = input("Enter password: ")
            login_response = stub.login(lms_pb2.LoginRequest(username=username, password=password))
            if login_response.status == "success":
                print(f"Student logged in with token: {login_response.token}")
                token = login_response.token

                while True:
                    print("\nLogged in as Student")
                    print("1. Upload Assignment")
                    print("2. View Course Materials")
                    print("3. View Grades")
                    print("4. Ask Question")
                    print("5. View feedback from instructor")
                    print("6. View Server Logs")    # New Option
                    print("7. Logout")
                    print("8. Exit")

                    sub_choice = input("Select an option: ")

                    if sub_choice == "1":
                        file_path = input("Enter the path to the assignment PDF: ")
                        with open(file_path, 'rb') as f:
                            data = f.read()
                        post_response = stub.post(lms_pb2.PostRequest(token=token, type="assignment", data=data))
                        print(post_response.status)

                    elif sub_choice == "2":
                        get_response = stub.get(lms_pb2.GetRequest(token=token, type="course_material"))
                        print(f"Course materials: {len(get_response.items)} found.")
                        for item in get_response.items:
                            with open(f"course_material_{item.id}.pdf", 'wb') as f:
                                f.write(item.data)
                            print(f"Saved course material from {item.id}.")

                    elif sub_choice == "3":
                        get_grades_response = stub.get(lms_pb2.GetRequest(token=token, type="grades"))
                        if len(get_grades_response.items) > 0:
                            grade_data = get_grades_response.items[0].data.decode("utf-8")
                            print(f"Your grade: {grade_data}")
                        else:
                            print("You have no grades yet.")

                    elif sub_choice == "4":
                        question = input("What is your question? ")
                        question_response = stub.askQuestion(lms_pb2.QuestionRequest(token=token, question=question))
                        print(f"LLM Response: {question_response.answer}")

                     
                    elif sub_choice == "5":
                         # Call the RPC to get feedback from the instructor
                        feedback_response = stub.get(lms_pb2.GetRequest(token=token, type="feedback"))  # Assuming you implement this in your server
                        if len(feedback_response.items) > 0:
                                feedback_message = feedback_response.items[0].data.decode("utf-8")
                                print(f"Feedback from instructor: {feedback_message}")
                        else:
                            print("No feedback from instructor yet.")
                         
                    elif sub_choice == "6":
                        view_logs(stub, token)     

                    elif sub_choice == "7":
                        logout_response = stub.logout(lms_pb2.LogoutRequest(token=token))
                        print("Logged out.")
                        break

                    elif sub_choice == "8":
                        print("Exiting.")
                        return

                    else:
                        print("Invalid option. Please try again.")

            else:
                print("Student login failed.")

        elif choice == "10":
            print("Exiting.")
            break

        else:
            print("Invalid option. Please try again.")

def run():
    servers = ['localhost:50051', 'localhost:50052', 'localhost:50053']
    token = None

    for server in servers:
        try:
            print(f"Connecting to server {server}")
            channel = grpc.insecure_channel(server)
            stub = lms_pb2_grpc.LMSStub(channel)
            student_menu(stub)
            break  # Exit after successfully displaying the menu

        except grpc.RpcError as e:
            print(f"Failed to connect to server {server}: {e}")
            continue  # Try the next server if connection fails

if __name__ == "__main__":
    run()
