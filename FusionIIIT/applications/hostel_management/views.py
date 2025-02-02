from django.core.serializers import serialize
from django.http import (
    HttpResponseBadRequest, JsonResponse, HttpResponse, HttpResponseRedirect,
)
from .models import (
    HostelLeave, HallCaretaker, HallWarden, StudentDetails, HostelNoticeBoard, Hall, Staff, HostelAllotment, HostelHistory, HostelTransactionHistory,GuestRoom,GuestRoomBooking, HostelComplaint
)
from applications.hostel_management.models import HallCaretaker, HallWarden
from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, APIException
from django.shortcuts import (
    redirect, get_object_or_404, render
)
from django.template import loader
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import IsAuthenticated
from django.urls import reverse
from rest_framework.authentication import (
    TokenAuthentication, BasicAuthentication
)
from .models import HostelFine, Student, Hall
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import (
    login_required, user_passes_test
)
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from applications.globals.models import (
    Designation, ExtraInfo, HoldsDesignation, DepartmentInfo, Faculty
)

from applications.academic_information.models import Student
import datetime
from datetime import time, date, datetime
from .forms import GuestRoomBookingForm, HostelNoticeBoardForm, HallForm
import xlrd
import re
import logging
from django.template.loader import get_template
from django.views.generic import View
from django.contrib import messages
from .utils import (
    render_to_pdf, save_worker_report_sheet, get_caretaker_hall,
    add_to_room, remove_from_room
)
from notification.views import hostel_notifications
from django.db.models.signals import post_save
from django.dispatch import receiver
import json
from Fusion.settings.common import LOGIN_URL
from time import localtime
from rest_framework.decorators import api_view, authentication_classes, permission_classes


def is_superuser(user):
    return user.is_authenticated and user.is_superuser


# //! My change
class GetIntenderId(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return JsonResponse(
                {"intender_id": request.user.id}, status=200
        )


@login_required
def hostel_view(request, context={}):
    """
    This is a general function which is used for all the views functions.
    This function renders all the contexts required in templates.
    @param:
        request - HttpRequest object containing metadata about the user request.
        context - stores any data passed during request,by default is empty.

    @variables:
        hall_1_student - stores all hall 1 students
        hall_3_student - stores all hall 3 students
        hall_4_student - stores all hall 4 students
        all_hall - stores all the hall of residence
        all_notice - stores all notices of hostels (latest first)
    """
    # Check if the user is a superuser
    is_superuser = request.user.is_superuser

    all_hall = Hall.objects.all()
    halls_student = {}
    for hall in all_hall:
        halls_student[hall.hall_id] = Student.objects.filter(
            hall_no=int(hall.hall_id[4])
        ).select_related("id__user")

    hall_staffs = {}
    for hall in all_hall:
        hall_staffs[hall.hall_id] = StaffSchedule.objects.filter(
            hall=hall
        ).select_related("staff_id__id__user")

    all_notice = HostelNoticeBoard.objects.all().order_by("-id")
    hall_notices = {}
    for hall in all_hall:
        hall_notices[hall.hall_id] = HostelNoticeBoard.objects.filter(
            hall=hall
        ).select_related("hall", "posted_by__user")

    pending_guest_room_requests = {}
    for hall in all_hall:
        pending_guest_room_requests[hall.hall_id] = GuestRoomBooking.objects.filter(
            hall=hall, status="Pending"
        ).select_related("hall", "intender")

    guest_rooms = {}
    for hall in all_hall:
        guest_rooms[hall.hall_id] = GuestRoom.objects.filter(
            hall=hall, vacant=True
        ).select_related("hall")
    user_guest_room_requests = GuestRoomBooking.objects.filter(
        intender=request.user
    ).order_by("-arrival_date")

    halls = Hall.objects.all()
    # Create a list to store additional details
    hostel_details = []

    # Loop through each hall and fetch assignedCaretaker and assignedWarden
    for hall in halls:
        try:
            caretaker = HallCaretaker.objects.filter(hall=hall).first()
            warden = HallWarden.objects.filter(hall=hall).first()
        except HostelAllotment.DoesNotExist:
            assigned_caretaker = None
            assigned_warden = None

        vacant_seat = hall.max_accomodation - hall.number_students
        hostel_detail = {
            "hall_id": hall.hall_id,
            "hall_name": hall.hall_name,
            "seater_type": hall.type_of_seater,
            "max_accomodation": hall.max_accomodation,
            "number_students": hall.number_students,
            "vacant_seat": vacant_seat,
            "assigned_batch": hall.assigned_batch,
            "assigned_caretaker": caretaker.staff.id.user.username
            if caretaker
            else None,
            "assigned_warden": warden.faculty.id.user.username if warden else None,
        }

        hostel_details.append(hostel_detail)

    Staff_obj = Staff.objects.all().select_related("id__user")
    hall1 = Hall.objects.get(hall_id="hall1")
    hall3 = Hall.objects.get(hall_id="hall3")
    hall4 = Hall.objects.get(hall_id="hall4")
    hall1_staff = StaffSchedule.objects.filter(hall=hall1)
    hall3_staff = StaffSchedule.objects.filter(hall=hall3)
    hall4_staff = StaffSchedule.objects.filter(hall=hall4)
    hall_caretakers = HallCaretaker.objects.all().select_related()
    hall_wardens = HallWarden.objects.all().select_related()
    all_students = Student.objects.all().select_related("id__user")
    all_students_id = []
    for student in all_students:
        all_students_id.append(student.id_id)

    hall_student = ""
    current_hall = ""
    get_avail_room = []
    get_hall = get_caretaker_hall(hall_caretakers, request.user)
    if get_hall:
        get_hall_num = re.findall("[0-9]+", str(get_hall.hall_id))
        hall_student = Student.objects.filter(
            hall_no=int(str(get_hall_num[0]))
        ).select_related("id__user")
        current_hall = "hall" + str(get_hall_num[0])

    for hall in all_hall:
        total_rooms = HallRoom.objects.filter(hall=hall)
        for room in total_rooms:
            if room.room_cap > room.room_occupied:
                get_avail_room.append(room)

    hall_caretaker_user = []
    for caretaker in hall_caretakers:
        hall_caretaker_user.append(caretaker.staff.id.user)

    hall_warden_user = []
    for warden in hall_wardens:
        hall_warden_user.append(warden.faculty.id.user)

    all_students = Student.objects.all().select_related("id__user")
    all_students_id = []
    for student in all_students:
        all_students_id.append(student.id_id)

    todays_date = date.today()
    current_year = todays_date.year
    current_month = todays_date.month

    if current_month != 1:
        worker_report = WorkerReport.objects.filter(
            Q(hall__hall_id=current_hall, year=current_year, month=current_month)
            | Q(hall__hall_id=current_hall, year=current_year, month=current_month - 1)
        )
    else:
        worker_report = WorkerReport.objects.filter(
            hall__hall_id=current_hall, year=current_year - 1, month=12
        )

    attendance = HostelStudentAttendence.objects.all().select_related()
    halls_attendance = {}
    for hall in all_hall:
        halls_attendance[hall.hall_id] = HostelStudentAttendence.objects.filter(
            hall=hall
        ).select_related()

    user_complaints = HostelComplaint.objects.filter(roll_number=request.user.username)
    user_leaves = HostelLeave.objects.filter(roll_num=request.user.username)
    my_leaves = []
    for leave in user_leaves:
        my_leaves.append(leave)
    my_complaints = []
    for complaint in user_complaints:
        my_complaints.append(complaint)

    all_leaves = HostelLeave.objects.all()
    all_complaints = HostelComplaint.objects.all()

    add_hostel_form = HallForm()
    warden_ids = Faculty.objects.all().select_related("id__user")

    # //! My change for imposing fines
    user_id = request.user
    staff_fine_caretaker = user_id.extrainfo.id
    students = Student.objects.all()

    fine_user = request.user

    if request.user.id in Staff.objects.values_list("id__user", flat=True):
        staff_fine_caretaker = request.user.extrainfo.id

        caretaker_fine_id = HallCaretaker.objects.filter(
            staff_id=staff_fine_caretaker
        ).first()
        if caretaker_fine_id:
            hall_fine_id = caretaker_fine_id.hall_id
            hostel_fines = HostelFine.objects.filter(hall_id=hall_fine_id).order_by(
                "fine_id"
            )
            context["hostel_fines"] = hostel_fines

    # caretaker_fine_id = HallCaretaker.objects.get(staff_id=staff_fine_caretaker)
    # hall_fine_id = caretaker_fine_id.hall_id
    # hostel_fines = HostelFine.objects.filter(hall_id=hall_fine_id).order_by('fine_id')

    if request.user.id in Staff.objects.values_list("id__user", flat=True):
        staff_inventory_caretaker = request.user.extrainfo.id

        caretaker_inventory_id = HallCaretaker.objects.filter(
            staff_id=staff_inventory_caretaker
        ).first()

        if caretaker_inventory_id:
            hall_inventory_id = caretaker_inventory_id.hall_id
            inventories = HostelInventory.objects.filter(
                hall_id=hall_inventory_id
            ).order_by("inventory_id")

            # Serialize inventory data
            inventory_data = []
            for inventory in inventories:
                inventory_data.append(
                    {
                        "inventory_id": inventory.inventory_id,
                        "hall_id": inventory.hall_id,
                        "inventory_name": inventory.inventory_name,
                        # Convert DecimalField to string
                        "cost": str(inventory.cost),
                        "quantity": inventory.quantity,
                    }
                )

            inventory_data.sort(key=lambda x: x["inventory_id"])
            context["inventories"] = inventory_data

    # all students details for caretaker and warden
    if request.user.id in Staff.objects.values_list("id__user", flat=True):
        staff_student_info = request.user.extrainfo.id

        if HallCaretaker.objects.filter(staff_id=staff_student_info).exists():
            hall_caretaker_id = HallCaretaker.objects.get(
                staff_id=staff_student_info
            ).hall_id

            hall_num = Hall.objects.get(id=hall_caretaker_id)
            hall_number = int("".join(filter(str.isdigit, hall_num.hall_id)))

            # hostel_students_details = Student.objects.filter(hall_no=hall_number)
            # context['hostel_students_details']= hostel_students_details

            hostel_students_details = []
            students = Student.objects.filter(hall_no=hall_number)

            a_room = []
            t_rooms = HallRoom.objects.filter(hall=hall_num)
            for room in t_rooms:
                if room.room_cap > room.room_occupied:
                    a_room.append(room)

            # Retrieve additional information for each student
            for student in students:
                student_info = {}
                student_info["student_id"] = student.id.id
                student_info["first_name"] = student.id.user.first_name
                student_info["programme"] = student.programme
                student_info["batch"] = student.batch
                student_info["hall_number"] = student.hall_no
                student_info["room_number"] = student.room_no
                student_info["specialization"] = student.specialization
                # student_info['parent_contact'] = student.parent_contact

                # Fetch address and phone number from ExtraInfo model
                extra_info = ExtraInfo.objects.get(user=student.id.user)
                student_info["address"] = extra_info.address
                student_info["phone_number"] = extra_info.phone_no

                hostel_students_details.append(student_info)

            # Sort the hostel_students_details list by roll number
            hostel_students_details = sorted(
                hostel_students_details, key=lambda x: x["student_id"]
            )

            context["hostel_students_details"] = hostel_students_details
            context["av_room"] = a_room

    if request.user.id in Faculty.objects.values_list("id__user", flat=True):
        staff_student_info = request.user.extrainfo.id
        if HallWarden.objects.filter(faculty_id=staff_student_info).exists():
            hall_warden_id = HallWarden.objects.get(
                faculty_id=staff_student_info
            ).hall_id

            hall_num = Hall.objects.get(id=hall_warden_id)

            hall_number = int("".join(filter(str.isdigit, hall_num.hall_id)))

            # hostel_students_details = Student.objects.filter(hall_no=hall_number)
            # context['hostel_students_details']= hostel_students_details

            hostel_students_details = []
            students = Student.objects.filter(hall_no=hall_number)

            # Retrieve additional information for each student
            for student in students:
                student_info = {}
                student_info["student_id"] = student.id.id
                student_info["first_name"] = student.id.user.first_name
                student_info["programme"] = student.programme
                student_info["batch"] = student.batch
                student_info["hall_number"] = student.hall_no
                student_info["room_number"] = student.room_no
                student_info["specialization"] = student.specialization
                # student_info['parent_contact'] = student.parent_contact

                # Fetch address and phone number from ExtraInfo model
                extra_info = ExtraInfo.objects.get(user=student.id.user)
                student_info["address"] = extra_info.address
                student_info["phone_number"] = extra_info.phone_no

                hostel_students_details.append(student_info)
                hostel_students_details = sorted(
                    hostel_students_details, key=lambda x: x["student_id"]
                )

            context["hostel_students_details"] = hostel_students_details

    if Student.objects.filter(id_id=request.user.username).exists():
        user_id = request.user.username
        student_fines = HostelFine.objects.filter(student_id=user_id)
        context["student_fines"] = student_fines

    hostel_transactions = HostelTransactionHistory.objects.order_by("-timestamp")

    # Retrieve all hostel history entries
    hostel_history = HostelHistory.objects.order_by("-timestamp")
    context = {
        "all_hall": all_hall,
        "all_notice": all_notice,
        "staff": Staff_obj,
        "hall1_staff": hall1_staff,
        "hall3_staff": hall3_staff,
        "hall4_staff": hall4_staff,
        "hall_caretaker": hall_caretaker_user,
        "hall_warden": hall_warden_user,
        "room_avail": get_avail_room,
        "hall_student": hall_student,
        "worker_report": worker_report,
        "halls_student": halls_student,
        "current_hall": current_hall,
        "hall_staffs": hall_staffs,
        "hall_notices": hall_notices,
        "attendance": halls_attendance,
        "guest_rooms": guest_rooms,
        "pending_guest_room_requests": pending_guest_room_requests,
        "user_guest_room_requests": user_guest_room_requests,
        "all_students_id": all_students_id,
        "is_superuser": is_superuser,
        "warden_ids": warden_ids,
        "add_hostel_form": add_hostel_form,
        "hostel_details": hostel_details,
        "all_students_id": all_students_id,
        "my_complaints": my_complaints,
        "my_leaves": my_leaves,
        "all_leaves": all_leaves,
        "all_complaints": all_complaints,
        "staff_fine_caretaker": staff_fine_caretaker,
        "students": students,
        "hostel_transactions": hostel_transactions,
        "hostel_history": hostel_history,
        **context,
    }

    return render(request, "hostelmanagement/hostel.html", context)


def staff_edit_schedule(request):
    """
    This function is responsible for creating a new or updating an existing staff schedule.
    @param:
       request - HttpRequest object containing metadata about the user request.

    @variables:
       start_time - stores start time of the schedule.
       end_time - stores endtime of the schedule.
       staff_name - stores name of staff.
       staff_type - stores type of staff.
       day - stores assigned day of the schedule.
       staff - stores Staff instance related to staff_name.
       staff_schedule - stores StaffSchedule instance related to 'staff'.
       hall_caretakers - stores all hall caretakers.
    """
    if request.method == "POST":
        start_time = datetime.datetime.strptime(
            request.POST["start_time"], "%H:%M"
        ).time()
        end_time = datetime.datetime.strptime(request.POST["end_time"], "%H:%M").time()
        staff_name = request.POST["Staff_name"]
        staff_type = request.POST["staff_type"]
        day = request.POST["day"]

        staff = Staff.objects.get(pk=staff_name)
        try:
            staff_schedule = StaffSchedule.objects.get(staff_id=staff)
            staff_schedule.day = day
            staff_schedule.start_time = start_time
            staff_schedule.end_time = end_time
            staff_schedule.staff_type = staff_type
            staff_schedule.save()
            messages.success(request, "Staff schedule updated successfully.")
        except:
            hall_caretakers = HallCaretaker.objects.all()
            get_hall = ""
            get_hall = get_caretaker_hall(hall_caretakers, request.user)
            StaffSchedule(
                hall=get_hall,
                staff_id=staff,
                day=day,
                staff_type=staff_type,
                start_time=start_time,
                end_time=end_time,
            ).save()
            messages.success(request, "Staff schedule created successfully.")
    return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))


def staff_delete_schedule(request):
    """
    This function is responsible for deleting an existing staff schedule.
    @param:
      request - HttpRequest object containing metadata about the user request.

    @variables:
      staff_dlt_id - stores id of the staff whose schedule is to be deleted.
      staff - stores Staff object related to 'staff_name'
      staff_schedule - stores staff schedule related to 'staff'
    """
    if request.method == "POST":
        staff_dlt_id = request.POST["dlt_schedule"]
        staff = Staff.objects.get(pk=staff_dlt_id)
        staff_schedule = StaffSchedule.objects.get(staff_id=staff)
        staff_schedule.delete()
    return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))

class NoticeBoardCreate(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self,request):
        """
        This function is used to create a form to show the notice on the Notice Board.
        @param:
            request - HttpRequest object containing metadata about the user request.

        @variables:
            hall - stores hall of residence related to the notice.
            head_line - stores headline of the notice.
            content - stores content of the notice.
            description - stores description of the notice.
            scope - stores the scope of the notice.
        """
        data = request.data

        hall = None
        hall_id = None
        # Get the hall_id of the logged-in user
        staff_student_info = request.user.extrainfo.id
        if HallWarden.objects.filter(faculty_id=staff_student_info).exists():
            hall = HallWarden.objects.filter(faculty_id=staff_student_info).first()
            hall_id = hall.hall.hall_id
        if(HallCaretaker.objects.filter(staff_id=staff_student_info).exists()):
            caretaker = HallCaretaker.objects.filter(staff_id=staff_student_info)
            if len(caretaker) != 0: hall_id = caretaker[0].hall.hall_id
        if(hall_id is None):
            hall = Student.objects.filter(id=staff_student_info).values("hall_id").first()
            if not hall: return JsonResponse({"error": "Hall ID not found for the user."}, status=404)
            hall_id = hall["hall_id"]
        if(hall_id is None): return JsonResponse({"error": "Hall ID not found for the user."}, status=404)
        hall = Hall.objects.get(hall_id=hall_id)
        posted_by = request.user.extrainfo
        head_line = request.data.get('headline', '')
        content = request.data.get('content','')
        description = request.data.get('description','')
        scope = '1' if request.data.get('scope') == "global" else '0'

        # Creating a new notice entry
        new_notice = HostelNoticeBoard.objects.create(
            hall=hall,
            posted_by=posted_by,
            head_line=head_line,
            content=content,
            description=description,
            scope=scope,
        )
        new_notice.save()
        messages.success(request, "Notice created successfully.")
        return Response({"status": "done"}, status=status.HTTP_201_CREATED)

    def get(self, request):
        return Response({"error": "Invalid request method"}, status=status.HTTP_400_BAD_REQUEST)

class NoticeBoardDelete(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        This function is responsible for deleting ana existing notice from the notice board.
        @param:
          request - HttpRequest object containing metadata about the user request.

        @variables:
          notice_id - stores id of the notice.
          notice - stores HostelNoticeBoard object related to 'notice_id'
        """

        notice_id = request.data.get("id")
        notice = HostelNoticeBoard.objects.get(pk=notice_id)
        notice.delete()
        return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))

    def get(self, request):
        return Response({"error": "Invalid request method"}, status=status.HTTP_400_BAD_REQUEST)

def edit_student_rooms_sheet(request):
    """
    This function is used to edit the room and hall of a multiple students.
    The user uploads a .xls file with Roll No, Hall No, and Room No to be updated.
    @param:
        request - HttpRequest object containing metadata about the user request.
    """
    if request.method == "POST":
        sheet = request.FILES["upload_rooms"]
        excel = xlrd.open_workbook(file_contents=sheet.read())
        all_rows = excel.sheets()[0]
        for row in all_rows:
            if row[0].value == "Roll No":
                continue
            roll_no = row[0].value
            hall_no = row[1].value
            if row[0].ctype == 2:
                roll_no = str(int(roll_no))
            if row[1].ctype == 2:
                hall_no = str(int(hall_no))

            room_no = row[2].value
            block = str(room_no[0])
            room = re.findall("[0-9]+", room_no)
            is_valid = True
            student = Student.objects.filter(id=roll_no.strip())
            hall = Hall.objects.filter(hall_id="hall" + hall_no[0])
            if student and hall.exists():
                Room = HallRoom.objects.filter(
                    hall=hall[0], block_no=block, room_no=str(room[0])
                )
                if Room.exists() and Room[0].room_occupied < Room[0].room_cap:
                    continue
                else:
                    is_valid = False
                    messages.error(request, "Room  unavailable!")
                    break
            else:
                is_valid = False
                messages.error(request, "Wrong credentials entered!")
                break

        if not is_valid:
            return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))

        for row in all_rows:
            if row[0].value == "Roll No":
                continue
            roll_no = row[0].value
            if row[0].ctype == 2:
                roll_no = str(int(roll_no))

            hall_no = str(int(row[1].value))
            room_no = row[2].value
            block = str(room_no[0])
            room = re.findall("[0-9]+", room_no)
            is_valid = True
            student = Student.objects.filter(id=roll_no.strip())
            remove_from_room(student[0])
            add_to_room(student[0], room_no, hall_no)
        messages.success(request, "Hall Room change successfull !")

        return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))


def edit_student_room(request):
    """
    This function is used to edit the room number of a student.
    @param:
      request - HttpRequest object containing metadata about the user request.

    @varibles:
      roll_no - stores roll number of the student.
      room_no - stores new room number.
      batch - stores batch number of the student generated from 'roll_no'
      students - stores students related to 'batch'.
    """
    if request.method == "POST":
        roll_no = request.POST["roll_no"]
        hall_room_no = request.POST["hall_room_no"]
        index = hall_room_no.find("-")
        room_no = hall_room_no[index + 1 :]
        hall_no = hall_room_no[:index]
        student = Student.objects.get(id=roll_no)
        remove_from_room(student)
        add_to_room(student, new_room=room_no, new_hall=hall_no)
        messages.success(request, "Student room changed successfully.")
        return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))


def edit_attendance(request):
    """
    This function is used to edit the attendance of a student.
    @param:
      request - HttpRequest object containing metadata about the user request.

    @variables:
      student_id = The student whose attendance has to be updated.
      hall = The hall of the concerned student.
      date = The date on which attendance has to be marked.
    """
    if request.method == "POST":
        roll_no = request.POST["roll_no"]

        student = Student.objects.get(id=roll_no)
        hall = Hall.objects.get(hall_id="hall" + str(student.hall_no))
        date = datetime.datetime.today().strftime("%Y-%m-%d")

        if (
            HostelStudentAttendence.objects.filter(
                student_id=student, date=date
            ).exists()
            == True
        ):
            messages.error(
                request, f"{student.id.id} is already marked present on {date}"
            )
            return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))

        record = HostelStudentAttendence.objects.create(
            student_id=student, hall=hall, date=date, present=True
        )
        record.save()

        messages.success(request, f"Attendance of {student.id.id} recorded.")

        return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))

@login_required
def generate_worker_report(request):
    if request.method == "POST":
        try:
            files = request.FILES.get("upload_report")
            if files:
                # Check if the file has a valid extension
                file_extension = files.name.split(".")[-1].lower()
                if file_extension not in ["xls", "xlsx"]:
                    messages.error(
                        request,
                        "Invalid file format. Please upload a .xls or .xlsx file.",
                    )
                    return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))

                excel = xlrd.open_workbook(file_contents=files.read())
                user_id = request.user.extrainfo.id
                for sheet in excel.sheets():
                    save_worker_report_sheet(excel, sheet, user_id)
                return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))
            else:
                messages.error(request, "No file uploaded")
        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")
    return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))


class GeneratePDF(View):
    def get(self, request, *args, **kwargs):
        """
        This function is used to generate worker report in pdf format available for download.
        @param:
          request - HttpRequest object containing metadata about the user request.

        @variables:
          months - stores number of months for which the authorized user wants to generate worker report.
          toadys_date - stores current date.
          current_year - stores current year retrieved from 'todays_date'.
          current_month - stores current month retrieved from 'todays_date'.
          template - stores template returned by 'get_template' method.
          hall_caretakers - stores all hall caretakers.
          worker_report - stores 'WorkerReport' instances according to 'months'.

        """
        months = int(request.GET.get("months"))
        todays_date = date.today()
        current_year = todays_date.year
        current_month = todays_date.month

        template = get_template("hostelmanagement/view_report.html")

        hall_caretakers = HallCaretaker.objects.all()
        get_hall = ""
        get_hall = get_caretaker_hall(hall_caretakers, request.user)
        if months < current_month:
            worker_report = WorkerReport.objects.filter(
                hall=get_hall,
            )
        else:
            worker_report = WorkerReport.objects.filter(
                Q(hall=get_hall, year=current_year, month__lte=current_month)
                | Q(
                    hall=get_hall,
                    year=current_year - 1,
                    month__gte=12 - months + current_month,
                )
            )

        worker = {"worker_report": worker_report}
        html = template.render(worker)
        pdf = render_to_pdf("hostelmanagement/view_report.html", worker)
        if pdf:
            response = HttpResponse(pdf, content_type="application/pdf")
            filename = "Invoice_%s.pdf" % ("12341231")
            content = "inline; filename='%s'" % (filename)
            download = request.GET.get("download")
            if download:
                content = "attachment; filename='%s'" % (filename)
            response["Content-Disposition"] = content
            return response
        return HttpResponse("Not found")


class NoticeBoardView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        hall = None
        hall_id = None
        # Get the hall_id of the logged-in user
        staff_student_info = request.user.extrainfo.id
        if(staff_student_info == "HostelSuperUser"):
            notices = HostelNoticeBoard.objects.filter(scope=1).values(
                "id", "hall", "posted_by", "head_line", "content", "description", "scope"
            )
            #.values("id", "hall", "posted_by", "head_line", "content", "description", "scope")
            data = list(notices)
            for notice in data:
                notice["hall_id"] = Hall.objects.filter(id=int(notice["hall"])).values("hall_id").first()["hall_id"]
            return JsonResponse(data, safe=False)


        else:
            if HallWarden.objects.filter(faculty_id=staff_student_info).exists():
                hall = HallWarden.objects.filter(faculty_id=staff_student_info).first()
                hall_id = hall.hall.hall_id
            if(HallCaretaker.objects.filter(staff_id=staff_student_info).exists()):
                caretaker = HallCaretaker.objects.filter(staff_id=staff_student_info)
                if len(caretaker) != 0: hall_id = caretaker[0].hall.hall_id
            if(hall_id is None):
                hall = Student.objects.filter(id=staff_student_info).values("hall_id").first()
                if not hall: return JsonResponse({"error": "Hall ID not found for the user."}, status=404)
                hall_id = hall["hall_id"]
            if(hall_id is None): return JsonResponse({"error": "Hall ID not found for the user."}, status=404)
            hall = Hall.objects.get(hall_id=hall_id)
            notices = HostelNoticeBoard.objects.filter(Q(hall = hall) | Q(scope=1)).values(
                "id", "hall", "posted_by", "head_line", "content", "description", "scope"
            )
            #.values("id", "hall", "posted_by", "head_line", "content", "description", "scope")
            data = list(notices)
            for notice in data:
                notice["hall_id"] = Hall.objects.filter(id=int(notice["hall"])).values("hall_id").first()["hall_id"]
            return JsonResponse(data, safe=False)

class AllLeaveData(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        try:
            staff = request.user.extrainfo.id
        except AttributeError:
            staff = None
        if staff is not None and HallCaretaker.objects.filter(staff_id=staff).exists():
            all_leave = list(
                HostelLeave.objects.values(
                    "id", "student_name", "roll_num", "reason", "start_date", "end_date", "status", "remark"
                )
            )
            return JsonResponse(all_leave, safe=False)
        
        
        else:
            return JsonResponse(
                {"error": "You are not authorized to access this page."}, status=403
            )

@csrf_exempt
def update_leave_status(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            leave_id = data.get("leave_id")
            status = data.get("status")
            remark = data.get("remark", "")

            leave = HostelLeave.objects.get(id=leave_id)
            leave.status = status
            leave.remark = remark
            leave.save()

            return JsonResponse(
                {
                    "status": "success",
                    "message": "Leave status updated successfully.",
                    "leave_id": leave_id,
                    "status_update": status,
                    "remark": remark,
                }
            )
        except HostelLeave.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "Leave not found."}, status=404
            )
        except Exception as e:
            return JsonResponse(
                {"status": "error", "message": str(e)}, status=500
            )
    else:
        return JsonResponse(
            {"status": "error", "message": "Only POST requests are allowed."},
            status=405,
        )

class CreateHostelLeave(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Parsing the request body
            data = json.loads(request.body.decode('utf-8'))

            # Extracting fields from the request
            student_name = data.get("student_name")
            roll_num = data.get("roll_num")
            phone_number = data.get("phone_number")
            reason = data.get("reason")
            start_date_str = data.get("start_date")
            end_date_str = data.get("end_date")

            # Initializing error dictionary
            errors = {}

            # Validation checks
            if not student_name:
                errors["student_name"] = "Student name is required."
            if not roll_num:
                errors["roll_num"] = "Roll number is required."
            if not phone_number or len(phone_number) != 10 or not phone_number.isdigit():
                errors["phone_number"] = "A valid 10-digit phone number is required."
            if not reason:
                errors["reason"] = "Reason is required."
            if not start_date_str:
                errors["start_date"] = "Start date is required."
            if not end_date_str:
                errors["end_date"] = "End date is required."

            # Parsing the date fields
            start_date = None
            end_date = None
            date_format = "%Y-%m-%d"

            if start_date_str and "start_date" not in errors:
                try:
                    start_date = datetime.strptime(start_date_str, date_format).date()
                except ValueError:
                    errors["start_date"] = "Start date must be in YYYY-MM-DD format."

            if end_date_str and "end_date" not in errors:
                try:
                    end_date = datetime.strptime(end_date_str, date_format).date()
                except ValueError:
                    errors["end_date"] = "End date must be in YYYY-MM-DD format."

            # Date comparison check
            if start_date and end_date and start_date > end_date:
                errors["date"] = "Start date cannot be later than the end date."

            # If there are validation errors, return 400 with the errors
            if errors:
                return JsonResponse({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

            # Creating the leave request entry in the database
            leave = HostelLeave.objects.create(
                student_name=student_name,
                roll_num=roll_num,
                phone_number=phone_number,
                reason=reason,
                start_date=start_date,
                end_date=end_date,
            )
            # Return success message after successful creation
            return JsonResponse(
                {"message": "Hostel leave request created successfully"},
                status=status.HTTP_201_CREATED,
            )

        except json.JSONDecodeError as e:
            # Log and return specific error if the JSON is malformed
            return JsonResponse({"error": "Invalid JSON format."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Log unexpected errors with stack trace for debugging
            return JsonResponse(
                {"error": "An unexpected error occurred while processing your request."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

# hostel_complaints_list caretaker can see all hostel complaints
@api_view(['GET'])
def hostel_complaint_list(request):
    """
    Fetches and returns all data entries related to the logged-in student based on roll_number.
    """
    try:
        # Get the logged-in user's roll number
        user_profile = request.user.extrainfo  # Assuming 'extrainfo' holds the user's profile data
        roll_number = user_profile.id
        # Fetching all the complaints for the logged-in student
        complaints = HostelComplaint.objects.filter(roll_number=roll_number.lower()).values(
            "id", "hall_name", "student_name", "roll_number", "description", "contact_number"
        )
        # Return the complaints as a JSON response
        return JsonResponse({"complaints": list(complaints)}, safe=False, status=200)

    except Exception as e:
        # Handle errors and send a failure response
        return JsonResponse({"error": str(e)}, status=500)
    
class HostelComplaintListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Fetches and returns all hostel complaints related to the logged-in user's roll number.
        """
        try:
            # Get the logged-in user's roll number
            user_profile = request.user.extrainfo  # Assuming the user's profile is stored in 'extrainfo'
            roll_number = user_profile.id

            # Fetch all hostel complaints related to the logged-in user's roll number
            complaints = HostelComplaint.objects.filter(roll_number=roll_number).values(
                "id", "hall_name", "student_name", "roll_number", "description", "contact_number"
            )
            # Return the complaints as a JSON response
            return JsonResponse({"complaints": list(complaints)}, safe=False, status=200)

        except Exception as e:
            # Log the exception and send an error response
            print(f"Error: {str(e)}")
            return JsonResponse({"error": str(e)}, status=500)

class students_get_students_info(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        """
        Fetches and returns student details for the hall associated with the requesting user.
        """
        try:
            hall = None
            hall_id = None
            # Get the hall_id of the logged-in user
            staff_student_info = request.user.extrainfo.id
            if HallWarden.objects.filter(faculty_id=staff_student_info).exists():
                hall = HallWarden.objects.filter(faculty_id=staff_student_info).first()
                hall_id = hall.hall.hall_id
            if(hall is None):
                hall = Student.objects.filter(id=staff_student_info).values("hall_id").first()
                if not hall:
                    return JsonResponse({"error": "Hall ID not found for the user."}, status=404)
                hall_id = hall["hall_id"]
            if(hall_id is None): return JsonResponse({"error": "Hall ID not found for the user."}, status=404)
            # Get the students in the same hall
            student_details = Student.objects.filter(hall_id=hall_id).values(
                "id__user__username",  # Assuming `id` is linked to `ExtraInfo` and `user`
                "programme",
                "batch",
                "cpi",
                "category",
                "father_name",
                "mother_name",
                "hall_id",
                "room_no",
                "specialization",
                "curr_semester_no",
            )
            # Return the data as a JSON response
            return JsonResponse(list(student_details), safe=False, status=200)
        
        except Exception as e:
            print(e)
            return JsonResponse({"error": str(e)}, status=500)


class caretaker_get_students_info(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        """
        Fetches and returns student details for the hall associated with the requesting caretaker.
        """
        try:
            hall_id = None
            user_id = request.user.id
            staff = request.user.extrainfo.id
            caretaker = HallCaretaker.objects.filter(staff_id=staff)
            # Check if the logged-in user is a Caretaker and get the hall_id
            if len(caretaker) != 0:  # User is a Caretaker
                hall_id = caretaker[0].hall.hall_id
            else:
                return JsonResponse({"error": "User is not a caretaker."}, status=403)
            
            if not hall_id:
                return JsonResponse({"error": "Hall ID not found for the caretaker."}, status=404)

            # Get the students in the same hall
            student_details = Student.objects.filter(hall_id=hall_id).values(
                "id__user__username",  # Assuming `id` is linked to `ExtraInfo` and `user`
                "programme",
                "batch",
                "cpi",
                "category",
                "father_name",
                "mother_name",
                "hall_id",
                "room_no",
                "specialization",
                "curr_semester_no",
            )
            
            # Return the data as a JSON response
            return JsonResponse(list(student_details), safe=False, status=200)
        
        except Exception as e:
            print(f"Error: {e}")
            return JsonResponse({"error": str(e)}, status=500)


class PostComplaint(APIView):
    # Assuming you are using session authentication
    authentication_classes = [TokenAuthentication]
    # Allow only authenticated users to access the view
    permission_classes = [IsAuthenticated]

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Redirect to the login page if user is not authenticated
            return redirect("/hostelmanagement")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, "hostelmanagement/post_complaint_form.html")

    def post(self, request):
        hall_name = request.data.get("hall_name")
        student_name = request.data.get("student_name")
        roll_number = request.data.get("roll_number")
        description = request.data.get("description")
        contact_number = request.data.get("contact_number")

        # Assuming the student's name is stored in the user object
        student_name = request.user.username

        complaint = HostelComplaint.objects.create(
            hall_name=hall_name,
            student_name=student_name,
            roll_number=roll_number,
            description=description,
            contact_number=contact_number,
        )

        # Use JavaScript to display a pop-up message after submission
        return HttpResponse(
            '<script>alert("Complaint submitted successfully"); window.location.href = "/hostelmanagement";</script>'
        )


# // student can see his leave status


class my_leaves(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request, *args, **kwargs):
        try:
            # Get the user ID from the request's user
            user_id = str(request.user.extrainfo.id)

            # Retrieve leaves registered by the current student based on their roll number
            my_leaves = HostelLeave.objects.filter(roll_num=user_id.lower()).values( "student_name", "roll_num", "reason", "phone_number", "start_date", "end_date", "status", "remark" )
            # Construct the context to pass to the template
            context = {"leaves": list(my_leaves)}
            # Render the template with the context data
            return JsonResponse(context, status=200)

        except User.DoesNotExist:
            # Handle the case where the user with the given ID doesn't exist
            return JsonResponse({"leaves": "na"}, status=403)

class HallIdView(APIView):
    authentication_classes = []  # Allow public access for testing
    permission_classes = []  # Allow any user to access the view

    def get(self, request, *args, **kwargs):
        hall_id = HostelAllotment.objects.values("hall_id")
        return Response(hall_id, status=status.HTTP_200_OK)


@login_required(login_url=LOGIN_URL)
def logout_view(request):
    logout(request)
    return redirect("/")

@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
class AssignCaretakerView(APIView):

    def get(self, request, *args, **kwargs):
        hall = Hall.objects.all()
        hall = list(hall.values())
        caretaker_usernames = Staff.objects.all()
        caretaker_usernames = list(caretaker_usernames.values())
        return JsonResponse({"halls": hall, "caretaker_usernames": caretaker_usernames}, status=status.HTTP_200_OK)


    def post(self, request, *args, **kwargs):
        hall_id = request.data.get("hall_id")
        caretaker_username = request.data.get("caretaker_username")

        try:
            hall = Hall.objects.get(hall_id=hall_id)
            caretaker_staff = Staff.objects.get(id__user__username=caretaker_username)

            # Retrieve the previous caretaker for the hall, if any
            prev_hall_caretaker = HallCaretaker.objects.filter(hall=hall).first()
            # Delete any previous assignments of the caretaker in HallCaretaker table
            HallCaretaker.objects.filter(staff=caretaker_staff).delete()

            # Delete any previous assignments of the caretaker in HostelAllotment table
            HostelAllotment.objects.filter(assignedCaretaker=caretaker_staff).delete()

            # Delete any previously assigned caretaker to the same hall
            HallCaretaker.objects.filter(hall=hall).delete()

            # Assign the new caretaker to the hall in HallCaretaker table
            hall_caretaker = HallCaretaker.objects.create(
                hall=hall, staff=caretaker_staff
            )

            # # Update the assigned caretaker in Hostelallottment table
            hostel_allotments = HostelAllotment.objects.filter(hall=hall)
            for hostel_allotment in hostel_allotments:
                hostel_allotment.assignedCaretaker = caretaker_staff
                hostel_allotment.save()

            # Retrieve the current warden for the hall
            current_warden = HallWarden.objects.filter(hall=hall).first()

            try:
                history_entry = HostelTransactionHistory.objects.create(
                    hall=hall,
                    change_type="Caretaker",
                    previous_value=prev_hall_caretaker.staff.id
                    if (prev_hall_caretaker and prev_hall_caretaker.staff)
                    else "None",
                    new_value=caretaker_username,
                )
            except Exception as e:
                print("Error creating HostelTransactionHistory:", e)

            # Create hostel history
            try:
                HostelHistory.objects.create(
                    hall=hall,
                    caretaker=caretaker_staff,
                    batch=hall.assigned_batch,
                    warden=current_warden.faculty
                    if (current_warden and current_warden.faculty)
                    else None,
                )
            except Exception as e:
                print("Error creating history", e)
            return Response(
                {
                    "message": f"Caretaker {caretaker_username} assigned to Hall {hall_id} successfully"
                },
                status=status.HTTP_201_CREATED,
            )

        except Hall.DoesNotExist:
            return Response(
                {"error": f"Hall with ID {hall_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Staff.DoesNotExist:
            return Response(
                {"error": f"Caretaker with username {caretaker_username} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return JsonResponse({"status": "error", "error": str(e)}, status=500)


class AssignBatchView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        hall = Hall.objects.all()
        hall = list(hall.values())
        return JsonResponse({"halls": hall}, status=status.HTTP_200_OK)

    def update_student_hall_allotment(self, hall, assigned_batch):
        hall_number = int("".join(filter(str.isdigit, hall.hall_id)))
        students = Student.objects.filter(batch=int(assigned_batch))

        for student in students:
            student.hall_no = hall_number
            student.save()

    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():  # Start a database transaction
                data = json.loads(request.body.decode("utf-8"))
                hall_id = data.get("hall_id")

                hall = Hall.objects.get(hall_id=hall_id)
                # previous_batch = hall.assigned_batch  # Get the previous batch
                previous_batch = (
                    hall.assigned_batch if hall.assigned_batch is not None else 0
                )  # Get the previous batch
                hall.assigned_batch = data.get("batch")
                hall.save()

                # Update the assignedBatch field in HostelAllotment table for the corresponding hall
                room_allotments = HostelAllotment.objects.filter(hall=hall)
                for room_allotment in room_allotments:
                    room_allotment.assignedBatch = hall.assigned_batch
                    room_allotment.save()

                # retrieve the current caretaker and current warden for the hall
                current_caretaker = HallCaretaker.objects.filter(hall=hall).first()
                current_warden = HallWarden.objects.filter(hall=hall).first()

                # Record the transaction history
                HostelTransactionHistory.objects.create(
                    hall=hall,
                    change_type="Batch",
                    previous_value=previous_batch,
                    new_value=hall.assigned_batch,
                )

                # Create hostel history
                try:
                    HostelHistory.objects.create(
                        hall=hall,
                        caretaker=current_caretaker.staff
                        if (current_caretaker and current_caretaker.staff)
                        else None,
                        batch=hall.assigned_batch,
                        warden=current_warden.faculty
                        if (current_warden and current_warden.faculty)
                        else None,
                    )
                except Exception as e:
                    print("Error creating history", e)

                self.update_student_hall_allotment(hall, hall.assigned_batch)
                messages.success(request, "batch assigned succesfully")

                return JsonResponse(
                    {"status": "success", "message": "Batch assigned successfully"},
                    status=200,
                )

        except Hall.DoesNotExist:
            return JsonResponse(
                {"status": "error", "error": f"Hall with ID {hall_id} not found"},
                status=404,
            )

        except Exception as e:
            print(e)
            return JsonResponse({"status": "error", "error": str(e)}, status=500)

class AssignWardenView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        hall = Hall.objects.all()
        hall = list(hall.values())
        warden_usernames = Faculty.objects.all().values()
        warden_usernames = list(warden_usernames)
        return JsonResponse({"halls": hall, "warden_usernames": warden_usernames}, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        hall_id = request.data.get("hall_id")
        warden_id = request.data.get("warden_username")
        try:
            hall = Hall.objects.get(hall_id=hall_id)
            warden = Faculty.objects.get(id__user__username=warden_id)

            # Retrieve the previous caretaker for the hall, if any
            prev_hall_warden = HallWarden.objects.filter(hall=hall).first()

            # Delete any previous assignments of the warden in Hallwarden table
            HallWarden.objects.filter(faculty=warden).delete()

            # Delete any previous assignments of the warden in HostelAllotment table
            HostelAllotment.objects.filter(assignedWarden=warden).delete()

            # Delete any previously assigned warden to the same hall
            HallWarden.objects.filter(hall=hall).delete()

            # Assign the new warden to the hall in Hallwarden table
            hall_warden = HallWarden.objects.create(hall=hall, faculty=warden)

            # current caretker
            current_caretaker = HallCaretaker.objects.filter(hall=hall).first()

            # Update the assigned warden in Hostelallottment table
            hostel_allotments = HostelAllotment.objects.filter(hall=hall)
            for hostel_allotment in hostel_allotments:
                hostel_allotment.assignedWarden = warden
                hostel_allotment.save()

            try:
                history_entry = HostelTransactionHistory.objects.create(
                    hall=hall,
                    change_type="Warden",
                    previous_value=prev_hall_warden.faculty.id
                    if (prev_hall_warden and prev_hall_warden.faculty)
                    else "None",
                    new_value=warden,
                )
            except Exception as e:
                print("Error creating HostelTransactionHistory:", e)

            # Create hostel history
            try:
                HostelHistory.objects.create(
                    hall=hall,
                    caretaker=current_caretaker.staff
                    if (current_caretaker and current_caretaker.staff)
                    else None,
                    batch=hall.assigned_batch,
                    warden=warden,
                )
            except Exception as e:
                print("Error creating history", e)

            return Response(
                {
                    "message": f"Warden {warden_id} assigned to Hall {hall_id} successfully"
                },
                status=status.HTTP_201_CREATED,
            )

        except Hall.DoesNotExist:
            return Response(
                {"error": f"Hall with ID {hall_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Faculty.DoesNotExist:
            return Response(
                {"error": f"Warden with username {warden_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return JsonResponse({"status": "error", "error": str(e)}, status=500)

@method_decorator(csrf_exempt, name="dispatch")  # Disable CSRF for API compatibility
class AddHostelView(View):
    def post(self, request, *args, **kwargs):
        import json
        data = json.loads(request.body)  # Parse JSON data from the React frontend
        form = HallForm(data)

        if form.is_valid():
            hall_id = form.cleaned_data["hall_id"]

            # Check if a hall with the given hall_id already exists
            if Hall.objects.filter(hall_id=hall_id).exists():
                return JsonResponse(
                    {"success": False, "message": f"Hall with ID {hall_id} already exists."},
                    status=400,
                )

            # If not, create a new hall
            form.save()
            return JsonResponse(
                {"success": True, "message": "Hall added successfully!"},
                status=201,
            )

        # If form is not valid, return errors
        return JsonResponse(
            {"success": False, "errors": form.errors},
            status=400,
        )
    
class CheckHallExistsView(View):
    def get(self, request, *args, **kwargs):
        hall_id = request.GET.get("hall_id")
        exists = Hall.objects.filter(hall_id=hall_id).exists()

        return JsonResponse({"exists": exists})



# @method_decorator(user_passes_test(is_superuser), name="dispatch")
class AdminHostelListView(View):
    def get(self, request, *args, **kwargs):
        halls = Hall.objects.all()
        # Create a list to store additional details
        hostel_details = []

        # Loop through each hall and fetch assignedCaretaker and assignedWarden
        for hall in halls:
            try:
                caretaker = HallCaretaker.objects.filter(hall=hall).first()
                warden = HallWarden.objects.filter(hall=hall).first()
            except HostelAllotment.DoesNotExist:
                assigned_caretaker = None
                assigned_warden = None

            hostel_detail = {
                "hall_id": hall.hall_id,
                "hall_name": hall.hall_name,
                "max_accomodation": hall.max_accomodation,
                "number_students": hall.number_students,
                "assigned_batch": hall.assigned_batch,
                "assigned_caretaker": caretaker.staff.id.user.username
                if caretaker
                else None,
                "assigned_warden": warden.faculty.id.user.username if warden else None,
            }

            hostel_details.append(hostel_detail)
        return JsonResponse({"hostel_details": hostel_details})


@method_decorator(user_passes_test(is_superuser), name="dispatch")
class DeleteHostelView(View):
    def get(self, request, hall_id, *args, **kwargs):
        # Get the hall instance
        hall = get_object_or_404(Hall, hall_id=hall_id)

        # Delete related entries in other tables
        hostelallotments = HostelAllotment.objects.filter(hall=hall)
        hostelallotments.delete()

        # Delete the hall
        hall.delete()
        messages.success(request, f"Hall {hall_id} deleted successfully.")

        return HttpResponseRedirect(reverse("hostelmanagement:hostel_view"))


class HallIdView(APIView):
    authentication_classes = []  # Allow public access for testing
    permission_classes = []  # Allow any user to access the view

    def get(self, request, *args, **kwargs):
        hall_id = HostelAllotment.objects.values("hall_id")
        return Response(hall_id, status=status.HTTP_200_OK)


@login_required(login_url=LOGIN_URL)
def logout_view(request):
    logout(request)
    return redirect("/")


# //! alloted_rooms
def alloted_rooms(request, hall_id):
    """
    This function returns the allotted rooms in a particular hall.

    @param:
      request - HttpRequest object containing metadata about the user request.
      hall_id - Hall ID for which the allotted rooms need to be retrieved.

    @variables:
      allotted_rooms - stores all the rooms allotted in the given hall.
    """
    # Query the hall by hall_id
    hall = Hall.objects.get(hall_id=hall_id)
    # Query all rooms allotted in the given hall
    allotted_rooms = HallRoom.objects.filter(hall=hall, room_occupied__gt=0)
    # Prepare a list of room details to be returned
    room_details = []
    for room in allotted_rooms:
        room_details.append(
            {
                "hall": room.hall.hall_id,
                "room_no": room.room_no,
                "block_no": room.block_no,
                "room_cap": room.room_cap,
                "room_occupied": room.room_occupied,
            }
        )
    return JsonResponse(room_details, safe=False)


def alloted_rooms_main(request):
    """
    This function returns the allotted rooms in all halls.

    @param:
      request - HttpRequest object containing metadata about the user request.

    @variables:
      all_halls - stores all the halls.
      all_rooms - stores all the rooms allotted in all halls.
    """
    # Query all halls
    all_halls = Hall.objects.all()

    # Query all rooms allotted in all halls
    all_rooms = []
    for hall in all_halls:
        all_rooms.append(HallRoom.objects.filter(hall=hall, room_occupied__gt=0))

    # Prepare a list of room details to be returned
    room_details = []
    for rooms in all_rooms:
        for room in rooms:
            room_details.append(
                {
                    "hall": room.hall.hall_name,
                    "room_no": room.room_no,
                    "block_no": room.block_no,
                    "room_cap": room.room_cap,
                    "room_occupied": room.room_occupied,
                }
            )

    # Return the room_details as JSON response
    return render(
        request,
        "hostelmanagement/alloted_rooms_main.html",
        {"allotted_rooms": room_details, "halls": all_halls},
    )


# //! all_staff
def all_staff(request, hall_id):
    """
    This function returns all staff information for a specific hall.

    @param:
      request - HttpRequest object containing metadata about the user request.
      hall_id - The ID of the hall for which staff information is requested.


    @variables:
      all_staff - stores all staff information for the specified hall.
    """

    # Query all staff information for the specified hall
    all_staff = StaffSchedule.objects.filter(hall_id=hall_id)

    # Prepare a list of staff details to be returned
    staff_details = []
    for staff in all_staff:
        staff_details.append(
            {
                "type": staff.staff_type,
                "staff_id": staff.staff_id_id,
                "hall_id": staff.hall_id,
                "day": staff.day,
                "start_time": staff.start_time,
                "end_time": staff.end_time,
            }
        )

    # Return the staff_details as JSON response
    return JsonResponse(staff_details, safe=False)


# //! Edit Stuff schedule
class StaffScheduleView(APIView):
    """
    API endpoint for creating or editing staff schedules.
    """

    authentication_classes = []  # Allow public access for testing
    permission_classes = []  # Allow any user to access the view

    def patch(self, request, staff_id):
        staff = get_object_or_404(Staff, pk=staff_id)
        staff_type = request.data.get("staff_type")
        start_time = request.data.get("start_time")
        end_time = request.data.get("end_time")
        day = request.data.get("day")

        if start_time and end_time and day and staff_type:
            # Check if staff schedule exists for the given day
            existing_schedule = StaffSchedule.objects.filter(staff_id=staff_id).first()
            if existing_schedule:
                existing_schedule.start_time = start_time
                existing_schedule.end_time = end_time
                existing_schedule.day = day
                existing_schedule.staff_type = staff_type
                existing_schedule.save()
                return Response(
                    {"message": "Staff schedule updated successfully."},
                    status=status.HTTP_200_OK,
                )
            else:
                # If staff schedule doesn't exist for the given day, return 404
                return Response(
                    {"error": "Staff schedule does not exist for the given day."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(
            {"error": "Please provide start_time, end_time, and day."},
            status=status.HTTP_400_BAD_REQUEST,
        )


# //! Hostel Inventory


@login_required
def get_inventory_form(request):
    user_id = request.user
    staff = user_id.extrainfo.id
    # Check if the user is present in the HallCaretaker table
    if HallCaretaker.objects.filter(staff_id=staff).exists():
        # If the user is a caretaker, allow access
        halls = Hall.objects.all()
        return render(request, "hostelmanagement/inventory_form.html", {"halls": halls})
    else:
        # If the user is not a caretaker, redirect to the login page
        # return redirect('login')  # Adjust 'login' to your login URL name
        return HttpResponse(
            f'<script>alert("You are not authorized to access this page"); window.location.href = "/hostelmanagement/"</script>'
        )


@login_required
def edit_inventory(request, inventory_id):
    # Retrieve hostel inventory object
    inventory = get_object_or_404(HostelInventory, pk=inventory_id)

    # Check if the user is a caretaker
    user_id = request.user
    staff_id = user_id.extrainfo.id

    if HallCaretaker.objects.filter(staff_id=staff_id).exists():
        halls = Hall.objects.all()

        # Prepare inventory data for rendering
        inventory_data = {
            "inventory_id": inventory.inventory_id,
            "hall_id": inventory.hall_id,
            "inventory_name": inventory.inventory_name,
            "cost": str(inventory.cost),  # Convert DecimalField to string
            "quantity": inventory.quantity,
        }

        # Render the inventory update form with inventory data
        return render(
            request,
            "hostelmanagement/inventory_update_form.html",
            {"inventory": inventory_data, "halls": halls},
        )
    else:
        # If the user is not a caretaker, show a message and redirect
        return HttpResponse(
            '<script>alert("You are not authorized to access this page"); window.location.href = "/hostelmanagement/"</script>'
        )


class HostelInventoryUpdateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, inventory_id):
        user_id = request.user
        staff_id = user_id.extrainfo.id

        if not HallCaretaker.objects.filter(staff_id=staff_id).exists():
            return Response(
                {"error": "You are not authorized to update this hostel inventory"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        hall_id = request.data.get("hall_id")
        inventory_name = request.data.get("inventory_name")
        cost = request.data.get("cost")
        quantity = request.data.get("quantity")

        # Validate required fields
        if not all([hall_id, inventory_name, cost, quantity]):
            return Response(
                {"error": "All fields are required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Retrieve hostel inventory object
        hostel_inventory = get_object_or_404(HostelInventory, pk=inventory_id)

        # Update hostel inventory object
        hostel_inventory.hall_id = hall_id
        hostel_inventory.inventory_name = inventory_name
        hostel_inventory.cost = cost
        hostel_inventory.quantity = quantity
        hostel_inventory.save()

        # Return success response
        return Response(
            {"message": "Hostel inventory updated successfully"},
            status=status.HTTP_200_OK,
        )


class HostelInventoryView(APIView):
    """
    API endpoint for CRUD operations on hostel inventory.
    """

    # permission_classes = [IsAuthenticated]

    # authentication_classes = []  # Allow public access for testing
    # permission_classes = []  # Allow any user to access the view

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, hall_id):
        user_id = request.user
        staff_id = user_id.extrainfo.id

        if not HallCaretaker.objects.filter(staff_id=staff_id).exists():
            return HttpResponse(
                '<script>alert("You are not authorized to access this page"); window.location.href = "/hostelmanagement/"</script>'
            )

        # Retrieve hostel inventory objects for the given hall ID
        inventories = HostelInventory.objects.filter(hall_id=hall_id)

        # Get all hall IDs
        halls = Hall.objects.all()

        # Serialize inventory data
        inventory_data = []
        for inventory in inventories:
            inventory_data.append(
                {
                    "inventory_id": inventory.inventory_id,
                    "hall_id": inventory.hall_id,
                    "inventory_name": inventory.inventory_name,
                    "cost": str(inventory.cost),  # Convert DecimalField to string
                    "quantity": inventory.quantity,
                }
            )

        inventory_data.sort(key=lambda x: x["inventory_id"])

        # Return inventory data as JSON response
        return render(
            request,
            "hostelmanagement/inventory_list.html",
            {"halls": halls, "inventories": inventory_data},
        )

    def post(self, request):
        user_id = request.user
        staff_id = user_id.extrainfo.id

        if not HallCaretaker.objects.filter(staff_id=staff_id).exists():
            return Response(
                {"error": "You are not authorized to create a new hostel inventory"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Extract data from request
        hall_id = request.data.get("hall_id")
        inventory_name = request.data.get("inventory_name")
        cost = request.data.get("cost")
        quantity = request.data.get("quantity")

        # Validate required fields
        if not all([hall_id, inventory_name, cost, quantity]):
            return Response(
                {"error": "All fields are required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Create hostel inventory object
        try:
            hostel_inventory = HostelInventory.objects.create(
                hall_id=hall_id,
                inventory_name=inventory_name,
                cost=cost,
                quantity=quantity,
            )
            return Response(
                {
                    "message": "Hostel inventory created successfully",
                    "hall_id": hall_id,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, inventory_id):
        user_id = request.user
        staff_id = user_id.extrainfo.id

        if not HallCaretaker.objects.filter(staff_id=staff_id).exists():
            return Response(
                {"error": "You are not authorized to delete this hostel inventory"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        inventory = get_object_or_404(HostelInventory, pk=inventory_id)
        inventory.delete()
        return Response(
            {"message": "Hostel inventory deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )


def update_allotment(request, pk):
    if request.method == "POST":
        try:
            allotment = HostelAllottment.objects.get(pk=pk)
        except HostelAllottment.DoesNotExist:
            return JsonResponse({"error": "HostelAllottment not found"}, status=404)

        try:
            allotment.assignedWarden = Faculty.objects.get(id=request.POST["warden_id"])
            allotment.assignedCaretaker = Staff.objects.get(
                id=request.POST["caretaker_id"]
            )
            allotment.assignedBatch = request.POST.get(
                "student_batch", allotment.assignedBatch
            )
            allotment.save()
            return JsonResponse({"success": "HostelAllottment updated successfully"})
        except (Faculty.DoesNotExist, Staff.DoesNotExist, IntegrityError):
            return JsonResponse(
                {"error": "Invalid data or integrity error"}, status=400
            )

    return JsonResponse({"error": "Invalid request method"}, status=405)

@api_view(['POST'])
@login_required
def request_guest_room(request):
    """
    This function is used by the student to book a guest room.
    """
    if request.method == 'POST':
        data = request.data
        
        # Extract the data
        hall = data['hall']
        guest_name = data['guest_name']
        guest_phone = data['guest_phone']
        guest_email = data['guest_email']
        guest_address = data['guest_address']
        rooms_required = data['rooms_required']
        total_guest = data['total_guest']
        purpose = data['purpose']
        arrival_date = data['arrival_date']
        arrival_time = data['arrival_time']
        departure_date = data['departure_date']
        departure_time = data['departure_time']
        nationality = data['nationality']
        room_type = data['room_type']
        
        max_guests = {
            "single": 1,
            "double": 2,
            "triple": 3,
        }
        
        # Check room availability
        available_rooms_count = GuestRoom.objects.filter(
            hall=int(hall), room_type=room_type, vacant=True
        ).count()

        if available_rooms_count < rooms_required:
            return Response({"error": "Not enough available rooms."}, status=status.HTTP_400_BAD_REQUEST)

        if total_guest > rooms_required * max_guests.get(room_type, 1):
            return Response({"error": "Number of guests exceeds the capacity of selected rooms."}, status=status.HTTP_400_BAD_REQUEST)

        # Create the booking
        newBooking = GuestRoomBooking.objects.create(
            hall=Hall.objects.filter(hall_id = int(hall)).values(),
            intender=request.user,
            guest_name=guest_name,
            guest_address=guest_address,
            guest_phone=guest_phone,
            guest_email=guest_email,
            rooms_required=rooms_required,
            total_guest=total_guest,
            purpose=purpose,
            arrival_date=arrival_date,
            arrival_time=arrival_time,
            departure_date=departure_date,
            departure_time=departure_time,
            nationality=nationality,
            room_type=room_type,
        )
        newBooking.save()

        # Notify the caretaker
        hall_caretaker = get_object_or_404(HallCaretaker, hall=hall)
        caretaker = hall_caretaker.staff.id.user
        # Send notification (implement `hostel_notifications` as needed)
        hostel_notifications(sender=request.user, recipient=caretaker, type="guestRoom_request")

        return Response({"message": "Room request submitted successfully!"}, status=status.HTTP_201_CREATED)
    

# api for fethching the guestroom booking request information form the guest room booking table ..........
class AllGuestRoomBookingData(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            staff = request.user.extrainfo.id
        except AttributeError:
            staff = None
        
        if staff is not None and HallCaretaker.objects.filter(staff_id=staff).exists():
            all_bookings = list(
                GuestRoomBooking.objects.values(
                    "id",
                    "guest_name",
                    "guest_phone",
                    "guest_email",
                    "guest_address",
                    "rooms_required",
                    "guest_room_id",
                    "total_guest",
                    "purpose",
                    "arrival_date",
                    "arrival_time",
                    "departure_date",
                    "departure_time",
                    "status",
                    "booking_date",
                    "nationality",
                    "room_type",
                )
            )
            return JsonResponse(all_bookings, safe=False)
        else:
            return JsonResponse(
                {"error": "You are not authorized to access this page."}, status=403
            )
        
class GetGuestRoomForStudents(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        all_bookings = list(
            GuestRoomBooking.objects.values(
                "id",
                "guest_name",
                "guest_phone",
                "guest_email",
                "guest_address",
                "rooms_required",
                "guest_room_id",
                "total_guest",
                "purpose",
                "arrival_date",
                "arrival_time",
                "departure_date",
                "departure_time",
                "status",
                "booking_date",
                "nationality",
                "room_type",
            )
        )
        return JsonResponse(all_bookings, safe=False)

@csrf_exempt
def update_guest_room_status(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            booking_id = data.get("booking_id")
            status = data.get("status")
            guest_room_id = data.get("guest_room_id", None)
            guest_room_request = GuestRoomBooking.objects.get(id=booking_id)

            if status.lower() == "accepted" and guest_room_id:
                guest_room_instance = GuestRoom.objects.get(
                    id=guest_room_id
                )
                if(guest_room_instance.vacant == False):
                    return JsonResponse(
                        {
                            "status": "notVacant",
                            "message": f"Guest room booking {status} not vacant.",
                            "booking_id": booking_id,
                            "status_update": status,
                            "guest_room_id": guest_room_id,
                        }
                        
                    )

                # Assign the guest room ID to guest_room_id field
                guest_room_request.guest_room_id = str(guest_room_instance.id)
                # Update guest room's occupancy details
                guest_room_instance.occupied_till = guest_room_request.departure_date
                guest_room_instance.vacant = False
                guest_room_instance.save()

            # Update status and save guest room request
            guest_room_request.status = status
            guest_room_request.save()

            return JsonResponse(
                {
                    "status": "success",
                    "message": f"Guest room booking {status} successfully.",
                    "booking_id": booking_id,
                    "status_update": status,
                    "guest_room_id": guest_room_id,
                }
                
            )
        except GuestRoomBooking.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "Guest room booking not found."},
                status=404,
            )
        except GuestRoom.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "Guest room not found."}, status=404
            )
        except Exception as e:
            print(e)
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    else:
        return JsonResponse(
            {"status": "error", "message": "Only POST requests are allowed."},
            status=405,
        )

def available_guestrooms_api(request):
    if request.method == "GET":
        hall_id = request.GET.get("hall_id")
        room_type = request.GET.get("room_type")

        if hall_id and room_type:
            available_rooms_count = GuestRoom.objects.filter(
                hall_id=hall_id, room_type=room_type, vacant=True
            ).count()
            return JsonResponse({"available_rooms_count": available_rooms_count})

    return JsonResponse({"error": "Invalid request"}, status=400)




# //! Manage Fine
# //! Add Fine Functionality
#
class ImposeFineView(APIView):
    """
    API endpoint to impose fines on students.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        This view is used to impose a fine on a student.
        """
        # Check if the required data is provided in the request
        student_id = request.data.get("studentId")
        fine_amount = request.data.get("fineAmount")
        fine_reason = request.data.get("fineReason")

        if not all([student_id, fine_amount, fine_reason]):
            return JsonResponse(
                {"error": "All fields (studentId, fineAmount, fineReason) are required."},
                status=400
            )

        try:
            # Fetch the student object based on student ID
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return JsonResponse(
                {"error": "Student not found."},
                status=404
            )

        # Get the hall from the student object (assuming student has a hall associated)
        hall_id = student.hall_id

        # Create the fine record
        fine = HostelFine.objects.create(
            student=student,
            hall=Hall.objects.filter(hall_id = hall_id)[0],
            student_name=student.id.user.username,  # Assuming student has a user field
            amount=fine_amount,
            reason=fine_reason,
            status="Pending"  # Default status is Pending
        )

        # Return success response
        return JsonResponse(
            {"message": "Fine imposed successfully.", "fineId": fine.fine_id},
            status=201
        )
##
@login_required
def show_fine_edit_form(request, fine_id):
    user_id = request.user
    staff = user_id.extrainfo.id
    caretaker = HallCaretaker.objects.get(staff_id=staff)
    hall_id = caretaker.hall_id

    fine = HostelFine.objects.filter(fine_id=fine_id)

    return render(request, "hostelmanagement/impose_fine_edit.html", {"fines": fine[0]})


@login_required
def update_student_fine(request, fine_id):
    if request.method == "POST":
        fine = HostelFine.objects.get(fine_id=fine_id)
        fine.amount = request.POST.get("amount")
        fine.status = request.POST.get("status")
        fine.reason = request.POST.get("reason")
        fine.save()

        return HttpResponse(
            {"message": "Fine has edited successfully"}, status=status.HTTP_200_OK
        )


@login_required
def impose_fine_view(request):
    user_id = request.user
    staff = user_id.extrainfo.id
    students = Student.objects.all()

    if HallCaretaker.objects.filter(staff_id=staff).exists():
        return render(
            request, "hostelmanagement/impose_fine.html", {"students": students}
        )

    return HttpResponse(
        f'<script>alert("You are not authorized to access this page"); window.location.href = "/hostelmanagement/"</script>'
    )


class HostelFineView(APIView):
    """
    API endpoint for imposing fines on students.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        # Check if the user is a caretaker
        user_id = request.user
        staff = user_id.extrainfo.id

        try:
            caretaker = HallCaretaker.objects.get(staff_id=staff)
        except HallCaretaker.DoesNotExist:
            return HttpResponse(
                f'<script>alert("You are not authorized to access this page"); window.location.href = "/hostelmanagement/"</script>'
            )

        hall_id = caretaker.hall_id

        # Extract data from the request
        student_id = request.data.get("student_id")
        student_name = request.data.get("student_fine_name")
        amount = request.data.get("amount")
        reason = request.data.get("reason")

        # Validate the data
        if not all([student_id, student_name, amount, reason]):
            return HttpResponse(
                {"error": "Incomplete data provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create the HostelFine object
        try:
            fine = HostelFine.objects.create(
                student_id=student_id,
                student_name=student_name,
                amount=amount,
                reason=reason,
                hall_id=hall_id,
            )
            # Sending notification to the student about the imposed fine

            recipient = User.objects.get(username=student_id)

            sender = request.user

            type = "fine_imposed"
            hostel_notifications(sender, recipient, type)

            return HttpResponse(
                {"message": "Fine imposed successfully."},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@login_required
def get_student_name(request, username):
    try:
        user = User.objects.get(username=username)
        full_name = (
            f"{user.first_name} {user.last_name}"
            if user.first_name or user.last_name
            else ""
        )
        return JsonResponse({"name": full_name})
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)


@login_required
def hostel_fine_list(request):
    user_id = request.user
    staff = user_id.extrainfo.id
    caretaker = HallCaretaker.objects.get(staff_id=staff)
    hall_id = caretaker.hall_id
    hostel_fines = HostelFine.objects.filter(hall_id=hall_id).order_by("fine_id")

    if HallCaretaker.objects.filter(staff_id=staff).exists():
        return render(
            request,
            "hostelmanagement/hostel_fine_list.html",
            {"hostel_fines": hostel_fines},
        )

    return HttpResponse(
        f'<script>alert("You are not authorized to access this page"); window.location.href = "/hostelmanagement/"</script>'
    )


@api_view(['GET'])
def student_fine_details(request):
    user_id = request.user.extrainfo.id
    # Check if user is authorized
    if not Student.objects.filter(id_id=user_id).exists():
        return Response({"error": "Unauthorized access"}, status=403)

    # Check if user has fines
    if not HostelFine.objects.filter(student__id_id=user_id).exists():
        return Response({"error": "No fines recorded"}, status=404)

    # Retrieve fines
    student_fines = HostelFine.objects.filter(student__id_id=user_id)
    fines_data = [
        {
            "fine_id": fine.fine_id,
            "student_name": fine.student_name,
            "hall": fine.hall.hall_id,  # Assuming Hall has a 'name' field
            "amount": str(fine.amount),  # Convert Decimal to string for JSON serialization
            "status": fine.status,
            "reason": fine.reason,
        }
        for fine in student_fines
    ]
    return Response({"student_fines": fines_data}, status=200)

    # return JsonResponse({'message': 'Nice'}, status=status.HTTP_200_OK)

##
class HostelFineListView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    def get(self, request):
        user_id = request.user
        staff = user_id.extrainfo.id

        try:
            caretaker = HallCaretaker.objects.get(staff_id=staff)
        except HallCaretaker.DoesNotExist:
            return Response({"error": "Unauthorized access"}, status=403)

        hall_id = caretaker.hall_id
        fines = HostelFine.objects.filter(hall_id=hall_id).values(
            "fine_id", "student_id", "amount", "status"
        )
        return Response({"fines": list(fines)}, status=200)
    

class HostelFineUpdateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Extract the fine_id from kwargs
        fine_id = kwargs.get("fine_id")
        if not fine_id:
            return Response({"error": "Fine ID is required."}, status=400)

        # Get the logged-in user's info
        user_id = request.user
        staff = user_id.extrainfo.id

        # Parse the incoming data
        data = request.data
        new_status = data.get("status")

        # Validate the status
        if new_status not in ["Pending", "Paid", "Unpaid"]:
            return Response(
                {"error": "Invalid status value. Only 'Pending', 'Paid', or 'Unpaid' are allowed."},
                status=400,
            )

        # Check if the user is a caretaker
        try:
            caretaker = HallCaretaker.objects.get(staff_id=staff)
        except HallCaretaker.DoesNotExist:
            return Response(
                {"error": "Unauthorized: Only caretakers can update fines."},
                status=403,
            )

        # Get the caretaker's hall ID
        hall_id = caretaker.hall_id

        # Check if the fine exists and belongs to the caretaker's hall
        try:
            fine = HostelFine.objects.get(fine_id=fine_id, hall_id=hall_id)
        except HostelFine.DoesNotExist:
            return Response(
                {"error": "Fine not found for the specified hall."},
                status=404,
            )

        # Check if the current fine status is different from the new status
        if fine.status == new_status:
            return Response(
                {"error": f"Fine ID {fine_id} already has the status '{new_status}'."},
                status=400,
            )

        # Update the fine status
        fine.status = new_status
        fine.save()

        # Return success response
        return Response(
            {"message": f"Fine ID {fine_id} status updated to '{new_status}' successfully."},
            status=200,
        )

class EditStudentView(View):
    template_name = "hostelmanagement/edit_student.html"

    def get(self, request, student_id):
        student = Student.objects.get(id=student_id)

        context = {"student": student}
        return render(request, self.template_name, context)

    def post(self, request, student_id):
        student = Student.objects.get(id=student_id)

        # Update student details
        student.id.user.first_name = request.POST.get("first_name")
        student.id.user.last_name = request.POST.get("last_name")
        student.programme = request.POST.get("programme")
        student.batch = request.POST.get("batch")
        student.hall_no = request.POST.get("hall_number")
        student.room_no = request.POST.get("room_number")
        student.specialization = request.POST.get("specialization")

        student.save()

        # Update phone number and address from ExtraInfo model
        student.id.phone_no = request.POST.get("phone_number")
        student.id.address = request.POST.get("address")
        student.id.save()
        student.save()
        messages.success(request, "Student details updated successfully.")
        return redirect("hostelmanagement:hostel_view")


class RemoveStudentView(View):
    def post(self, request, student_id):
        try:
            student = Student.objects.get(id=student_id)
            student.hall_no = 0
            student.save()
            messages.success(request, "Student removed successfully.")
            return redirect("hostelmanagement:hostel_view")
            return JsonResponse(
                {"status": "success", "message": "Student removed successfully"}
            )
        except Student.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "Student not found"}, status=404
            )
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    def dispatch(self, request, *args, **kwargs):
        if request.method != "POST":
            return JsonResponse(
                {"status": "error", "message": "Method Not Allowed"}, status=405
            )
        return super().dispatch(request, *args, **kwargs)
