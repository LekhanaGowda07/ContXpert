
import sys
import db


def unlink_student(usn):
    usn = usn.strip().upper()

    try:
        # Find existing WhatsApp registration
        user = db.get_user_by_usn(usn)

        if not user:
            print(f"No WhatsApp number is linked to {usn}.")
            return

        phone = user["phone"]

        print("\nExisting registration found:")
        print("USN:", usn)
        print("Phone:", phone)
        print("Registered at:", user.get("registered_at"))

        confirm = input("\nAre you sure you want to unlink? (yes/no): ")

        if confirm.strip().lower() != "yes":
            print("Operation cancelled.")
            return

        # Use the actual function defined in your db.py
        deleted = db.unbind_user(usn=usn)

        if deleted:
            # Clear the old WhatsApp conversation session
            db.clear_session(phone)

            print("\nSuccessfully unlinked!")
            print("USN:", usn)
            print("Old WhatsApp number:", phone)
            print("Registration session cleared.")
            print("\nThe student can now register again.")
        else:
            print("No registration was deleted.")

    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        student_usn = sys.argv[1]
    else:
        student_usn = input("Enter student USN: ")

    unlink_student(student_usn)
