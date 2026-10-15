import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from app.main import app

def main():
    client = TestClient(app)
    r = client.get('/api/v1/special-trainings')
    trainings = r.json()
    print('Trainings count:', len(trainings))
    if not trainings:
        print('No trainings found.')
        return

    t = trainings[0]
    t_id = t['id']
    print('Training:', t['name'], 'Initial subjects_count:', t.get('subjects_count'))

    # Check if any exist
    existing = client.get(f'/api/v1/special-trainings/{t_id}/subjects').json()
    print('Existing subjects:', len(existing))

    if len(existing) == 0:
        # Create 2 subjects
        s1 = client.post(f'/api/v1/special-trainings/{t_id}/subjects', json={
            'name': 'Quantitative Aptitude & Logical Reasoning',
            'code': 'APT101',
            'trainer_name': 'Prof. Rajesh Kumar',
            'venue': 'Auditorium Hall A',
            'description': 'Speed math, number series, logical deductions'
        }).json()
        print('Created s1:', s1['name'])

        s2 = client.post(f'/api/v1/special-trainings/{t_id}/subjects', json={
            'name': 'Full Stack Web & Cloud Architectures',
            'code': 'FSW201',
            'trainer_name': 'Dr. Alan Turing',
            'venue': 'Computing Lab 3',
            'description': 'React, FastAPI, and Cloud microservices'
        }).json()
        print('Created s2:', s2['name'])

    # Verify list
    subjects = client.get(f'/api/v1/special-trainings/{t_id}/subjects').json()
    print('Subjects count in DB for training:', len(subjects))
    for s in subjects:
        print(f" - {s['name']} (Code: {s['code']}) Trainer: {s['trainer_name']} Venue: {s['venue']}")

    # Check updated training response
    updated_t = client.get(f'/api/v1/special-trainings/{t_id}').json()
    print('Updated subjects_count on training:', updated_t.get('subjects_count'))

if __name__ == '__main__':
    main()
