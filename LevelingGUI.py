import tkinter as tk
import serial
import threading
import motion
import time

# Adjust your serial port and baud rate
SERIAL_PORT = 'COM5'
BAUD_RATE = 9600
MOTORS_PORT='COM4' 
EMULATE=False

class ArduinoController:
    def __init__(self, port, baud):
        self.ser = serial.Serial(port, baud, timeout=1)
        self.running = True
        self.interrupt_callback = None
        self.thread = threading.Thread(target=self.listen)
        self.thread.daemon = True
        self.thread.start()

    def send_command(self, command):
        self.ser.write((str(command) + '\n').encode())

    def listen(self):
        while self.running:
            try:
                line = self.ser.readline().decode().strip()
                if line == "INTERRUPT" and self.interrupt_callback:
                    self.interrupt_callback()
            except Exception as e:
                print("Serial error:", e)

    def close(self):
        self.running = False
        self.ser.close()

class App(tk.Tk):
    def __init__(self, arduino):
        super().__init__()
        self.arduino = arduino
        self.motors = motion.motion(port=MOTORS_PORT, emulate=EMULATE)
        self.title("Arduino Serial Control GUI")

        self.interrupt_label = tk.Label(self, text="Interrupt Status: Waiting...")
        self.interrupt_label.pack(pady=10)
        self.interruptFlag = threading.Event()


        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        #lower probe button
        btn_11 = tk.Button(btn_frame, text="Drop Probe", width=10, command=lambda: self.arduino.send_command(11))
        btn_11.pack(side=tk.LEFT, padx=5)
        #raise probe button
        btn_22 = tk.Button(btn_frame, text="Raise Probe", width=10, command=lambda: self.arduino.send_command(22))
        btn_22.pack(side=tk.LEFT, padx=5)
        
    
        #motor movement init
        self.stepSizeXY = 1
        self.stepSizeZ = 1
        self.stepSizeVarXY=tk.StringVar() 
        self.stepSizeVarZ=tk.StringVar()
        self.stepSizeVarXY.set(str(self.stepSizeXY))
        self.stepSizeVarZ.set(str(self.stepSizeZ))
        
        fieldxy_frame = tk.Frame(self)
        fieldxy_frame.pack(side=tk.LEFT, padx=10) 
        #xy movement fields and labels
        stepsLabelXY = tk.Label(fieldxy_frame, text="XY step [mm]")
        stepsLabelXY.pack()
        self.stepsEntryXY = tk.Entry(fieldxy_frame, textvariable=self.stepSizeVarXY, width=5)
        self.stepsEntryXY.pack()
        
        fieldz_frame = tk.Frame(self)
        fieldz_frame.pack(side=tk.LEFT, padx=10) 
        #z movement fields and labels
        stepsLabelZ = tk.Label(fieldz_frame, text="Z step [mm]")
        stepsLabelZ.pack()
        self.stepsEntryZ = tk.Entry(fieldz_frame, textvariable=self.stepSizeVarZ, width=5)
        self.stepsEntryZ.pack()
        
        
        # --- Direction + Raise/Lower Controls ---
        control_frame = tk.Frame(self)
        control_frame.pack(pady=20)

        # Directional pad using grid
        dpad_frame = tk.Frame(control_frame)
        dpad_frame.pack(side=tk.LEFT, padx=20)

        # Arrow Buttons (like keyboard arrows)
        btn_up = tk.Button(dpad_frame, text="↑", width=5, command=lambda: self.mv_platform('y',-float(self.stepsEntryXY.get())))
        btn_up.grid(row=0, column=1)

        btn_left = tk.Button(dpad_frame, text="←", width=5, command=lambda: self.mv_platform('x', -float(self.stepsEntryXY.get())))
        btn_left.grid(row=1, column=0)

        btn_down = tk.Button(dpad_frame, text="↓", width=5, command=lambda: self.mv_platform('y',float(self.stepsEntryXY.get())))
        btn_down.grid(row=1, column=1)

        btn_right = tk.Button(dpad_frame, text="→", width=5, command=lambda: self.mv_platform('x', float(self.stepsEntryXY.get())))
        btn_right.grid(row=1, column=2)

        # Raise/Lower stacked buttons
        vertical_frame = tk.Frame(control_frame)
        vertical_frame.pack(side=tk.LEFT)

        btn_raise = tk.Button(vertical_frame, text="Raise", width=10, command=lambda: self.mv_platform('z', float(self.stepsEntryZ.get())))
        btn_raise.pack(pady=5)

        btn_lower = tk.Button(vertical_frame, text="Lower", width=10, command=lambda: self.mv_platform('z', -float(self.stepsEntryZ.get())))
        btn_lower.pack(pady=5)
        
        #trial measurements frame1
        self.ntrial = 1
        self.ntrialVar=tk.StringVar() 
        self.ntrialVar.set(str(self.ntrial))
        single_trial_frame = tk.Frame(self)
        single_trial_frame.pack(side=tk.LEFT,  padx=10 )
        #ntrial entry field
        nTrialLabel = tk.Label(single_trial_frame, text="N meas. per position")
        nTrialLabel.pack()
        self.nTrialEntry = tk.Entry(single_trial_frame, textvariable=self.ntrialVar, width=5)
        self.nTrialEntry.pack()
        
        #trial button frame
        trial_btn_frame = tk.Frame(self)
        trial_btn_frame.pack(side=tk.LEFT,  padx=10 )
        #ntrial entry field
        btn_zero_in = tk.Button(trial_btn_frame, text="zero in", width=10, command=lambda: self.on_zero_in(1))
        btn_zero_in.pack(pady=5)
      
        btn_single_trial = tk.Button(trial_btn_frame, text="position ensemble", width=20, command=lambda: self.run_position_ensemble(1))
        btn_single_trial.pack(pady=5)
        
        self.final_positions = []

        self.arduino.interrupt_callback = self.on_interrupt

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_interrupt(self):
        self.after(0, lambda: self.interrupt_label.config(text="⚠️ Interrupt! Stopping motors."))
        #self.interrupt_label.config(text="Interrupt Triggered!")
        self.interruptFlag.set()
        self.after(4000, lambda: self.interrupt_label.config(text="Interrupt Status: Waiting..."))
        print("interrupt detected")

    def mv_platform(self,axis,step):
        self.motors.moveFor(axis,step)
     

    def on_closing(self):
        self.arduino.close()
        self.destroy()
     
    def recursive_step_motor(self, stepsize, on_complete=None):
        
        if self.interruptFlag.is_set():
            traveled = self.step_index * stepsize
            print("Aborting steps, on interrupt")
            print("step_index=",self.step_index)
            on_complete(traveled)
            return
        if self.step_index >= self.total_steps:
            traveled = self.step_index * stepsize
            print("covered full step range")
            on_complete(traveled)
            return
        print(f"Step {self.step_index}")
        self.step_index += 1
        self.mv_platform('z',stepsize)
        self.after(1500, lambda: self.recursive_step_motor(stepsize, on_complete))
        
    def run_trial( self, stepsize, total_steps, trial_index, on_done=None):
        
        self.interruptFlag.clear()
        self.step_index=0
        self.total_steps = total_steps
        def done(traveled):
            self.positions.append(traveled-stepsize)
            cumulative = sum(self.positions)
            print(f"Trial {trial_index} finished. Poistion = {traveled:.3f} mm")
            print(f"Cumulative position = {cumulative:.3f} mm")
            
            #Return paltform down to home +1mm
            self.mv_platform('z', -(cumulative+1.0))
           
            #after return completes, call on_done
            self.after(3000, lambda: on_done(cumulative))
        self.recursive_step_motor(stepsize, on_complete=done)
        
    def between_trials(self, next_start_pos, text_trial_func):
        print("Returning platform down to home...")
        
        def deploy_probe():
            print("Deploying probe...")
            self.arduino.send_command(11)
            self.after(1000,move_to_start)
        def move_to_start():
            print(f"Moving to start position: {next_start_pos:.3f}mm")
            self.mv_platform('z', next_start_pos)
            
        self.after(3000, deploy_probe)
        
    def run_trials(self, meas_num=0, on_trials_done=None):
         #reset positions
        self.positions=[]
        step_sizes = [1.0, 0.1, 0.01, 0.004]
        total_steps = [25, 20, 20, 20]
         
        def run_next(i):
            if i>= len(step_sizes):
                print("All trials complete!")
                print("Positions:", self.positions)
                print("Final cumulative-", sum(self.positions)+0.004)
                if on_trials_done:
                    on_trials_done(sum(self.positions)+0.004)
                return
            stepsize = step_sizes[i]
            steps = total_steps[i]
            
            def launch_trial():
                print(f"Starting trial {i+1} with step = {stepsize}")
                self.run_trial(stepsize, steps, i+1, on_done=lambda _: run_next(i+1))
                
            if i==0:
                launch_trial()
            else:
                start_pos = sum(self.positions)# - (step_sizes[i-1]*1.5)
                self.between_trials(start_pos, launch_trial)
                print(f"Starting trial {i+1} with step= {stepsize}")
                #self.run_trial(stepsize, steps, i+1, on_done=lambda _: run_next(i+1))
                self.after(5000, lambda: self.run_trial(stepsize, steps, i+1, on_done=lambda _: run_next(i+1)))
                
      
        run_next(0)
        
         
    #does one single measurement with 4 "precision bit" trials
    def on_zero_in(self, verbosity=1):
    
        if(verbosity==1):
            print("zeroing in")
        #move by mm until interrupt then reset
        #deploy the probe
        self.arduino.send_command(11)
        
        #reset the collective final positions of all meaurements
        self.final_positions=[]
        self.run_trials()
    
    #do an ensemble of single measurements each with 4 "precision bit" trials
    def run_position_ensemble(self, verbosity=1):
        print("performing single measurement with N=",self.ntrial)
        self.arduino.send_command(11)

        self.final_positions = []
        self.ntrial = int(self.nTrialEntry.get())
        n_measurements = self.ntrial
       
        def run_one(idx):
            self.arduino.send_command(11)
            print(f"\n=== Ensemble Run{idx+1}/{n_measurements} ===")
            
            def trials_done(final_pos):
                print(f"Ensemble run {idx+1} finished. Final position = {final_pos:.4f} mm")
                self.final_positions.append(final_pos)
                
                if idx+1 < n_measurements:
                    self.arduino.send_command(11)
                    self.after(2000, lambda: run_one(idx+1))
                else:
                    print(self.final_positions)
            self.run_trials(on_trials_done=trials_done)
        run_one(0)

    
    #def on_single_meas(self, ntrial):
        #print("performing single measurement with ntrials=",ntrial)

if __name__ == "__main__":
    arduino = ArduinoController(SERIAL_PORT, BAUD_RATE)
    app = App(arduino)
    app.mainloop()