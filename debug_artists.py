
from app import get_artists, find_artisan_match

print("--- Inspecting get_artists() ---")
artists = get_artists()
print(f"Total artists: {len(artists)}")
if len(artists) > 0:
    print("First artist keys:", artists[0].keys())
    print("First artist:", artists[0])

# Check if ANY artist has a 'name' key
names = [a.get('name') for a in artists if a.get('name')]
print(f"Artists with 'name' key: {len(names)}")
if names:
    print("Sample names:", names[:5])

print("\n--- Testing find_artisan_match ---")
match = find_artisan_match("Bamboo", "Traditional")
print("Match for Bamboo/Traditional:", match)
