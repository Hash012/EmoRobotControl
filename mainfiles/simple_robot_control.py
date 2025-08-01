#!/usr/bin/env python3
"""
Simple Robot Control Script for Seeed Studio Robotics Arm

This script provides basic control functions for your Fashion Star servo-based robot arm.
It's designed to be simple and easy to understand.

Usage:
    python3 simple_robot_control.py
"""

import time
import sys
import numpy as np

# Import robot configuration
try:
    from config import SERIAL_CONFIG, MOTOR_CONFIG, ROBOT_CONFIG
except ImportError:
    print("❌ Could not import config.py. Make sure it's in the same directory.")
    sys.exit(1)

# Try to import required modules
try:
    import fashionstar_uart_sdk as uservo
    import serial
except ImportError:
    print("❌ Missing required modules. Install with:")
    print("pip install fashionstar-uart-sdk pyserial")
    sys.exit(1)


class SimpleRobotController:
    """Simple controller for Fashion Star servo-based robot arm."""
    
    def __init__(self, port=None, baudrate=None):
        """
        Initialize the robot controller.
        
        Args:
            port: USB port for the robot arm (uses config default if None)
            baudrate: Communication baudrate (uses config default if None)
        """
        self.port = port or SERIAL_CONFIG.DEFAULT_PORT
        self.baudrate = baudrate or SERIAL_CONFIG.BAUDRATE
        self.uart = None
        self.servo_manager = None
        self.is_connected = False
        
        # Import motor configuration from config.py
        self.motor_ids = MOTOR_CONFIG.MOTOR_IDS.copy()
        self.joint_limits = MOTOR_CONFIG.JOINT_LIMITS.copy()
        self.home_position = MOTOR_CONFIG.HOME_POSITION.copy()
        
        # Current positions
        self.current_positions = {joint: 0.0 for joint in self.motor_ids.keys()}
        
        # Track which servos are responding
        self.responding_servos = set()
    
    def connect(self):
        """Connect to the robot arm."""
        try:
            print(f"🔌 Connecting to robot at {self.port}...")
            
            # Initialize serial connection
            self.uart = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=serial.PARITY_NONE,
                stopbits=1,
                bytesize=8,
                timeout=0.1
            )
            
            # Initialize servo manager
            self.servo_manager = uservo.UartServoManager(self.uart)
            
            # Reset multi-turn angles
            time.sleep(0.005)
            self.servo_manager.reset_multi_turn_angle(0xff)
            time.sleep(0.01)
            
            self.is_connected = True
            print("✅ Successfully connected to robot!")
            
            # Detect which servos are responding
            self.detect_servos()
            
            # Read initial positions
            self.read_positions()
            return True
            
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            print("Check that:")
            print(f"  - Robot is connected to {self.port}")
            print("  - Robot is powered on")
            print("  - USB port has correct permissions")
            return False
    
    def disconnect(self):
        """Disconnect from the robot arm."""
        if self.uart and self.uart.is_open:
            self.uart.close()
            self.is_connected = False
            print("✅ Disconnected from robot")
    
    def detect_servos(self):
        """Detect which servos are connected and responding."""
        print("🔍 Detecting connected servos...")
        self.responding_servos.clear()
        
        for joint, motor_id in self.motor_ids.items():
            try:
                # Try to ping the servo
                angle = self.servo_manager.query_servo_angle(motor_id)
                if angle is not None:
                    self.responding_servos.add(motor_id)
                    print(f"✅ {joint} (ID: {motor_id}) - responding")
                else:
                    print(f"❌ {joint} (ID: {motor_id}) - not responding")
            except Exception as e:
                print(f"❌ {joint} (ID: {motor_id}) - error: {e}")
        
        print(f"📊 Found {len(self.responding_servos)}/{len(self.motor_ids)} responding servos")
        
        if len(self.responding_servos) == 0:
            print("⚠️  No servos are responding. Check:")
            print("   - Power supply to servos")
            print("   - Servo ID configuration (should be 0-6)")
            print("   - Communication wiring")
            print("   - Baudrate settings")
    
    def read_positions(self):
        """Read current positions from all servos."""
        if not self.is_connected:
            print("❌ Robot not connected")
            return
        
        try:
            successful_reads = 0
            for joint, motor_id in self.motor_ids.items():
                try:
                    # Read current angle
                    angle = self.servo_manager.query_servo_angle(motor_id)
                    if angle is not None:
                        self.current_positions[joint] = angle
                        successful_reads += 1
                    else:
                        print(f"⚠️  No response from {joint} (ID: {motor_id})")
                except Exception as e:
                    print(f"⚠️  Failed to read {joint} (ID: {motor_id}): {e}")
            
            if successful_reads > 0:
                print(f"📍 Current positions ({successful_reads}/{len(self.motor_ids)} servos): {self.current_positions}")
            else:
                print("❌ No servos responded. Check connections and power.")
            
        except Exception as e:
            print(f"❌ Failed to read positions: {e}")
    
    def move_servo(self, motor_id, angle, speed=100):
        """
        Move a single servo to target angle.
        
        Args:
            motor_id: Motor ID (0-6)
            angle: Target angle in degrees
            speed: Movement speed (0-1000)
        """
        if not self.is_connected:
            print("❌ Robot not connected")
            return False
        
        try:
            # First check if servo is responding
            current_angle = self.servo_manager.query_servo_angle(motor_id)
            if current_angle is None:
                print(f"⚠️  Servo {motor_id} not responding - attempting to move anyway")
            
            # Set servo angle with speed control
            result = self.servo_manager.set_servo_angle(motor_id, angle, speed)
            
            # Give servo time to start moving
            time.sleep(0.1)
            
            # Verify the command was received (optional)
            new_angle = self.servo_manager.query_servo_angle(motor_id)
            if new_angle is not None and abs(new_angle - angle) > 5:
                print(f"⚠️  Servo {motor_id} may not have reached target angle (target: {angle}°, actual: {new_angle}°)")
            
            return True
        except Exception as e:
            print(f"❌ Failed to move servo {motor_id}: {e}")
            return False
    
    def move_joint(self, joint_name, angle, speed=100):
        """
        Move a joint to target angle with safety checks.
        
        Args:
            joint_name: Joint name (e.g., 'joint1', 'gripper')
            angle: Target angle in degrees
            speed: Movement speed (0-1000)
        """
        if joint_name not in self.motor_ids:
            print(f"❌ Unknown joint: {joint_name}")
            return False
        
        motor_id = self.motor_ids[joint_name]
        
        # Check if servo is responding
        if motor_id not in self.responding_servos:
            print(f"⚠️  {joint_name} (ID: {motor_id}) is not responding - skipping movement")
            return False
        
        # Check limits
        min_angle, max_angle = self.joint_limits[joint_name]
        if angle < min_angle or angle > max_angle:
            print(f"❌ Angle {angle}° out of range for {joint_name} ({min_angle}° to {max_angle}°)")
            return False
        
        if self.move_servo(motor_id, angle, speed):
            self.current_positions[joint_name] = angle
            print(f"✅ Moved {joint_name} to {angle}°")
            return True
        
        return False
    
    def move_multiple_joints(self, joint_angles, speed=100):
        """
        Move multiple joints simultaneously.
        
        Args:
            joint_angles: Dictionary of joint names and target angles
            speed: Movement speed (0-1000)
        """
        print(f"🤖 Moving joints: {joint_angles}")
        
        success = True
        for joint, angle in joint_angles.items():
            if not self.move_joint(joint, angle, speed):
                success = False
        
        return success
    
    def go_home(self):
        """Move robot to home position."""
        print("🏠 Moving to home position...")
        return self.move_multiple_joints(self.home_position, speed=50)
    
    def open_gripper(self):
        """Open the gripper."""
        return self.move_joint("gripper", MOTOR_CONFIG.GRIPPER_OPEN, speed=100)
    
    def close_gripper(self):
        """Close the gripper."""
        return self.move_joint("gripper", MOTOR_CONFIG.GRIPPER_CLOSED, speed=100)
    
    def demo_sequence(self):
        """Run a demonstration sequence."""
        print("🎭 Starting demo sequence...")
        
        sequences = [
            ("Home position", {"joint1": 0, "joint2": 0, "joint3": -90, "joint4": 0, "joint5": 0, "joint6": 0}),
            ("Wave hello", {"joint1": 45, "joint2": -30, "joint3": -60, "joint4": 30, "joint5": 0, "joint6": 0}),
            ("Reach forward", {"joint1": 0, "joint2": 30, "joint3": -45, "joint4": 15, "joint5": 0, "joint6": 0}),
            ("Side reach", {"joint1": 90, "joint2": 0, "joint3": -90, "joint4": 0, "joint5": 0, "joint6": 0}),
            ("Return home", {"joint1": 0, "joint2": 0, "joint3": -90, "joint4": 0, "joint5": 0, "joint6": 0}),
        ]
        
        for description, positions in sequences:
            print(f"📍 {description}")
            self.move_multiple_joints(positions, speed=80)
            time.sleep(2)  # Wait between movements
        
        print("✅ Demo sequence completed!")
    
    def interactive_control(self):
        """Interactive control mode."""
        print("\n🎮 Interactive Control Mode")
        print("Commands:")
        print("  move <joint> <angle>  - Move joint to angle (e.g., 'move joint1 45')")
        print("  home                  - Go to home position")
        print("  demo                  - Run demo sequence")
        print("  open                  - Open gripper")
        print("  close                 - Close gripper")
        print("  status                - Show current positions")
        print("  detect                - Re-detect servos")
        print("  troubleshoot          - Run servo diagnostics")
        print("  quit                  - Exit")
        print()
        
        while True:
            try:
                command = input("Robot> ").strip().lower()
                
                if command == "quit":
                    break
                elif command == "home":
                    self.go_home()
                elif command == "demo":
                    self.demo_sequence()
                elif command == "open":
                    self.open_gripper()
                elif command == "close":
                    self.close_gripper()
                elif command == "status":
                    self.read_positions()
                elif command == "detect":
                    self.detect_servos()
                elif command == "troubleshoot":
                    self.troubleshoot_servos()
                elif command.startswith("move"):
                    parts = command.split()
                    if len(parts) == 3:
                        joint = parts[1]
                        try:
                            angle = float(parts[2])
                            self.move_joint(joint, angle)
                        except ValueError:
                            print("❌ Invalid angle value")
                    else:
                        print("❌ Usage: move <joint> <angle>")
                else:
                    print("❌ Unknown command")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error: {e}")
        
        print("👋 Exiting interactive mode")
    
    def troubleshoot_servos(self):
        """Troubleshoot servo communication issues."""
        print("\n🔧 Servo Troubleshooting")
        print("=" * 40)
        
        if not self.is_connected:
            print("❌ Robot not connected")
            return
        
        print("Testing each servo individually...")
        
        for joint, motor_id in self.motor_ids.items():
            print(f"\n🔍 Testing {joint} (ID: {motor_id}):")
            
            try:
                # Test 1: Query angle
                angle = self.servo_manager.query_servo_angle(motor_id)
                if angle is not None:
                    print(f"  ✅ Query angle: {angle}°")
                else:
                    print(f"  ❌ Query angle: No response")
                    continue
                
                # Test 2: Small movement
                print(f"  🔄 Testing small movement...")
                original_angle = angle
                test_angle = angle + 5  # Small 5-degree movement
                
                # Check limits
                min_angle, max_angle = self.joint_limits[joint]
                if test_angle > max_angle:
                    test_angle = angle - 5
                
                if min_angle <= test_angle <= max_angle:
                    self.servo_manager.set_servo_angle(motor_id, test_angle, 50)
                    time.sleep(1)
                    
                    # Check if it moved
                    new_angle = self.servo_manager.query_servo_angle(motor_id)
                    if new_angle is not None:
                        if abs(new_angle - test_angle) < 3:
                            print(f"  ✅ Movement test: Success ({original_angle}° → {new_angle}°)")
                        else:
                            print(f"  ⚠️  Movement test: Partial ({original_angle}° → {new_angle}°, target: {test_angle}°)")
                    else:
                        print(f"  ❌ Movement test: No response after movement")
                    
                    # Return to original position
                    self.servo_manager.set_servo_angle(motor_id, original_angle, 50)
                    time.sleep(0.5)
                else:
                    print(f"  ⚠️  Skipping movement test (would exceed limits)")
                
            except Exception as e:
                print(f"  ❌ Error testing {joint}: {e}")
        
        print(f"\n📊 Summary: {len(self.responding_servos)}/{len(self.motor_ids)} servos responding")
        
        if len(self.responding_servos) < len(self.motor_ids):
            print("\n🔧 Troubleshooting tips for non-responding servos:")
            print("1. Check power supply (servos need adequate power)")
            print("2. Verify servo IDs are set correctly (0-6)")
            print("3. Check communication wiring")
            print("4. Try different baudrate (currently using 1,000,000)")
            print("5. Check if servos are in the correct mode")
            print("6. Verify servo firmware compatibility")


def main():
    """Main function."""
    print("🤖 Simple Robot Control for Seeed Studio Robotics Arm")
    print("=" * 60)
    
    # Configuration is now loaded from config.py
    print(f"📍 Using port: {SERIAL_CONFIG.DEFAULT_PORT}")
    print(f"📡 Baudrate: {SERIAL_CONFIG.BAUDRATE}")
    
    # Create controller (uses config.py settings)
    controller = SimpleRobotController()
    
    try:
        # Connect to robot
        if not controller.connect():
            print("❌ Failed to connect to robot. Exiting.")
            return
        
        # Show menu
        print("\nWhat would you like to do?")
        print("1. Interactive control")
        print("2. Run demo sequence")
        print("3. Go to home position")
        print("4. Test gripper")
        print("5. Troubleshoot servos")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            controller.interactive_control()
        elif choice == "2":
            controller.demo_sequence()
        elif choice == "3":
            controller.go_home()
        elif choice == "4":
            print("Testing gripper...")
            controller.open_gripper()
            time.sleep(2)
            controller.close_gripper()
            time.sleep(2)
            controller.move_joint("gripper", 0)  # Neutral position
        elif choice == "5":
            controller.troubleshoot_servos()
        else:
            print("Invalid choice")
    
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        controller.disconnect()
        print("👋 Goodbye!")


if __name__ == "__main__":
    main()