from socket import *
import os
import sys
import struct
import time
import select

ICMP_ECHO_REQUEST = 8

# ICMP type 3 (Destination Unreachable) codes
UNREACHABLE_CODES = {
    0: "Destination Network Unreachable",
    1: "Destination Host Unreachable",
    2: "Destination Protocol Unreachable",
    3: "Destination Port Unreachable",
    4: "Fragmentation Required",
    5: "Source Route Failed",
}


def checksum(data):
    """Internet checksum over a bytes object (Python 3 safe)."""
    csum = 0
    countTo = (len(data) // 2) * 2
    for count in range(0, countTo, 2):
        csum += (data[count] << 8) + data[count + 1]
    if countTo < len(data):
        csum += data[-1] << 8
    csum = (csum >> 16) + (csum & 0xFFFF)
    csum += csum >> 16
    return ~csum & 0xFFFF


def getInnerID(recPacket, ipHeaderLen):
    """Ambil ID dari ICMP asli yang ikut dibawa di dalam paket error (type 3 / 11)."""
    try:
        innerIpLen = (recPacket[ipHeaderLen + 8] & 0x0F) * 4
        start = ipHeaderLen + 8 + innerIpLen
        return struct.unpack("!H", recPacket[start + 4:start + 6])[0]
    except (IndexError, struct.error):
        return None


def receiveOnePing(mySocket, ID, timeout, destAddr):
    timeLeft = timeout
    while 1:
        startedSelect = time.time()
        whatReady = select.select([mySocket], [], [], timeLeft)
        howLongInSelect = time.time() - startedSelect
        if whatReady[0] == []:  # Timeout
            return None, "Request timed out."

        timeReceived = time.time()
        recPacket, addr = mySocket.recvfrom(1024)

        # Fill in start
        # IP header length (IHL = low nibble byte 0, satuan 32-bit word)
        ipHeaderLen = (recPacket[0] & 0x0F) * 4
        ttl = recPacket[8]

        # Fetch the ICMP header from the IP packet
        icmpHeader = recPacket[ipHeaderLen:ipHeaderLen + 8]
        icmpType, code, recvChecksum, packetID, sequence = struct.unpack("!BBHHH", icmpHeader)

        if icmpType == 0 and packetID == ID:  # Echo reply buat ping kita
            timeSent = struct.unpack("d", recPacket[ipHeaderLen + 8:ipHeaderLen + 16])[0]
            rtt = (timeReceived - timeSent) * 1000  # ms
            size = len(recPacket) - ipHeaderLen
            return rtt, "Reply from %s: bytes=%d time=%.2f ms TTL=%d" % (addr[0], size, rtt, ttl)

        if icmpType == 3 and getInnerID(recPacket, ipHeaderLen) == ID:  # Destination Unreachable
            msg = UNREACHABLE_CODES.get(code, "Destination Unreachable (code %d)" % code)
            return None, "Reply from %s: %s" % (addr[0], msg)

        if icmpType == 11 and getInnerID(recPacket, ipHeaderLen) == ID:  # TTL exceeded
            return None, "Reply from %s: Time to live exceeded" % addr[0]
        # Fill in end

        timeLeft = timeLeft - howLongInSelect
        if timeLeft <= 0:
            return None, "Request timed out."


def sendOnePing(mySocket, destAddr, ID):
    # Header: type (8), code (8), checksum (16), id (16), sequence (16)
    myChecksum = 0
    # Dummy header dengan checksum 0 ("!" = network byte order)
    header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, myChecksum, ID, 1)
    data = struct.pack("d", time.time())

    # Checksum dihitung dari header + data
    myChecksum = checksum(header + data)
    header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, myChecksum, ID, 1)

    packet = header + data
    mySocket.sendto(packet, (destAddr, 1))  # alamat AF_INET harus tuple


def doOnePing(destAddr, timeout):
    icmp = getprotobyname("icmp")
    # SOCK_RAW butuh root/administrator
    mySocket = socket(AF_INET, SOCK_RAW, icmp)
    try:
        myID = os.getpid() & 0xFFFF
        sendOnePing(mySocket, destAddr, myID)
        return receiveOnePing(mySocket, myID, timeout, destAddr)
    finally:
        mySocket.close()


def ping(host, timeout=1, count=None):
    # timeout=1: kalau 1 detik nggak ada balasan, dianggap paket hilang
    try:
        dest = gethostbyname(host)
    except gaierror:
        print("Host tidak ditemukan:", host)
        return

    print("Pinging " + host + " [" + dest + "] using Python:")
    print("")

    sent = 0
    rtts = []
    try:
        while count is None or sent < count:
            rtt, message = doOnePing(dest, timeout)
            print(message)
            sent += 1
            if rtt is not None:
                rtts.append(rtt)
            time.sleep(1)  # jeda 1 detik antar ping
    except KeyboardInterrupt:
        pass

    # Statistik (opsional 1)
    print("\n--- %s ping statistics ---" % host)
    if sent:
        loss = (sent - len(rtts)) / sent * 100
        print("%d packets transmitted, %d received, %.1f%% packet loss" % (sent, len(rtts), loss))
        if rtts:
            print("rtt min/avg/max = %.2f/%.2f/%.2f ms" % (min(rtts), sum(rtts) / len(rtts), max(rtts)))


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    ping(target, count=10)