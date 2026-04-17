"""
Shared booking logic for all business types.
Works for restaurants, oil change shops, clinics, salons, etc.
"""
from datetime import date, datetime
from typing import Optional
from .supabase_client import get_client

MAX_WAITLIST = 5


def check_availability(business_id: str, appt_date: str, appt_time: str) -> dict:
    """
    Check if a slot is available for a given business, date, and time.
    Returns: {available: bool, slots_left: int, waitlist_count: int}
    """
    db = get_client()

    # Count confirmed appointments for this slot
    result = db.table("appointments") \
        .select("id", count="exact") \
        .eq("business_id", business_id) \
        .eq("appointment_date", appt_date) \
        .eq("appointment_time", appt_time) \
        .in_("status", ["confirmed"]) \
        .execute()

    booked = result.count or 0

    # Get business capacity for this slot
    biz = db.table("businesses").select("settings").eq("id", business_id).single().execute()
    capacity = biz.data.get("settings", {}).get("slot_capacity", 1) if biz.data else 1

    # Count waitlist
    waitlist = db.table("waitlist") \
        .select("id", count="exact") \
        .eq("business_id", business_id) \
        .eq("requested_date", appt_date) \
        .eq("status", "waiting") \
        .execute()

    waitlist_count = waitlist.count or 0

    return {
        "available": booked < capacity,
        "slots_left": max(0, capacity - booked),
        "waitlist_count": waitlist_count,
        "waitlist_full": waitlist_count >= MAX_WAITLIST,
    }


def book_appointment(
    business_id: str,
    customer_name: str,
    customer_phone: str,
    appt_date: str,
    appt_time: str,
    party_size: int = 1,
    notes: str = "",
    metadata: dict = None,
) -> dict:
    """
    Book an appointment. Returns booking confirmation or waitlist info.
    Works for any business type — extra details go in metadata.
    """
    db = get_client()
    avail = check_availability(business_id, appt_date, appt_time)

    if avail["available"]:
        result = db.table("appointments").insert({
            "business_id": business_id,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "appointment_date": appt_date,
            "appointment_time": appt_time,
            "party_size": party_size,
            "status": "confirmed",
            "notes": notes,
            "metadata": metadata or {},
        }).execute()

        appt = result.data[0] if result.data else {}
        return {
            "status": "confirmed",
            "id": appt.get("id"),
            "message": f"Confirmed! Booking #{appt.get('id', '')[:8].upper()} for {customer_name} on {appt_date} at {appt_time}.",
        }

    # Slot full — try waitlist
    if avail["waitlist_full"]:
        return {
            "status": "full",
            "message": f"I'm sorry, that slot is fully booked and the waitlist is also full. Would you like to try a different time?",
        }

    # Add to waitlist
    position = avail["waitlist_count"] + 1
    result = db.table("waitlist").insert({
        "business_id": business_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "requested_date": appt_date,
        "requested_time": appt_time,
        "party_size": party_size,
        "position": position,
        "status": "waiting",
        "notes": notes,
    }).execute()

    return {
        "status": "waitlisted",
        "position": position,
        "message": f"That slot is full, but I've added {customer_name} to the waitlist at position {position} of {MAX_WAITLIST}. We'll call if a spot opens up!",
    }


def get_available_slots(business_id: str, appt_date: str, open_time: str = "17:00", close_time: str = "22:00", slot_duration_minutes: int = 90) -> list:
    """
    Return all available time slots for a business on a given date.
    Generates slots from open_time to close_time at slot_duration_minutes intervals.
    """
    from datetime import datetime, timedelta
    start = datetime.strptime(open_time, "%H:%M")
    end = datetime.strptime(close_time, "%H:%M")
    available = []
    current = start
    while current < end:
        slot_time = current.strftime("%H:%M")
        result = check_availability(business_id, appt_date, slot_time)
        if result["available"]:
            available.append(slot_time)
        current += timedelta(minutes=slot_duration_minutes)
    return available


def cancel_appointment(appointment_id: str) -> dict:
    """Cancel a booking and promote the first waitlisted customer."""
    db = get_client()

    appt = db.table("appointments").select("*").eq("id", appointment_id).single().execute()
    if not appt.data:
        return {"status": "error", "message": "Booking not found."}

    db.table("appointments").update({"status": "cancelled"}).eq("id", appointment_id).execute()

    # Promote first person on waitlist for same slot
    waitlist = db.table("waitlist") \
        .select("*") \
        .eq("business_id", appt.data["business_id"]) \
        .eq("requested_date", appt.data["appointment_date"]) \
        .eq("status", "waiting") \
        .order("position") \
        .limit(1) \
        .execute()

    if waitlist.data:
        promoted = waitlist.data[0]
        db.table("waitlist").update({"status": "notified"}).eq("id", promoted["id"]).execute()
        return {
            "status": "cancelled",
            "promoted": promoted["customer_name"],
            "message": f"Booking cancelled. {promoted['customer_name']} from the waitlist has been notified.",
        }

    return {"status": "cancelled", "message": "Booking cancelled successfully."}


def get_appointments(business_id: str, appt_date: str) -> list:
    """Get all confirmed appointments for a business on a given date."""
    db = get_client()
    result = db.table("appointments") \
        .select("*") \
        .eq("business_id", business_id) \
        .eq("appointment_date", appt_date) \
        .eq("status", "confirmed") \
        .order("appointment_time") \
        .execute()
    return result.data or []
