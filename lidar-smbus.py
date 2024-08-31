import smbus
import asyncio
from aiohttp import web
import aiohttp_cors
from rplidar import RPLidar, RPLidarException
import json
import threading

bus = smbus.SMBus(1)
address = 8


def send_data_to_arduino(data):
    bus.write_byte(address, data)
    print("raspberry pi sent: ", data)

lidar = RPLidar('/dev/ttyUSB0', 256000, 5, None)
scan_data = []
data_lock = threading.Lock()

def process_lidar_data_sync():
    global scan_data
    try:
        for scan in lidar.iter_scans():
            one_sent = False
            last_angle = None
            temp_scan_data = []

            for d in scan:
                angle = d[1]
                distance = d[2]

                if 270 <= angle <= 360 and 0 <= angle <= 90:
                    if (distance / 10) <= 200:
                        temp_scan_data.append({'angle': angle, 'distance': distance / 10})

                if last_angle is not None and abs((last_angle - d[1]) % 360) > 355:
                    with data_lock:
                        temp_scan_data.sort(key=lambda x: x['angle'])
                        scan_data = temp_scan_data.copy()
                last_angle = d[1]

            one_sent = False

            for d in scan:
                angle = d[1]
                distance = d[2]

                if 350 <= angle <= 360 and 0 <= angle <= 10:
                    if (distance / 10) <= 100:
                        one_sent = True
                        print(1)
                        send_data_to_arduino(1)
                        break
                    else:
                        one_sent = False

                if last_angle is not None and abs((last_angle - angle) % 360) > 355:
                    one_sent = False

            if not one_sent:
                print(0)
                send_data_to_arduino(0)
                one_sent = False

    except RPLidarException as err:
        print(err)
    except KeyboardInterrupt:
        print('Keyboard interrupt')
    finally:
        lidar.stop()
        lidar.stop_motor()
        lidar.disconnect()

async def handle_request(request):
    with data_lock:
        response_body = json.dumps(scan_data).encode('utf-8')
        scan_data.clear()
    return web.Response(body=response_body, content_type='application/json')

async def main():
    lidar.connect()
    info = lidar.get_info()
    print(info)
    health = lidar.get_health()
    print(health)

    app = web.Application()

    cors = aiohttp_cors.setup(app)
    cors.add(app.router.add_get('/', handle_request), {
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 9000)
    await site.start()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, process_lidar_data_sync)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Program interrupted')
        lidar.stop()
        lidar.stop_motor()
        lidar.disconnect()
