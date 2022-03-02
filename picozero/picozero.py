from machine import Pin, PWM, Timer, ADC
from time import ticks_ms, sleep

class PWMChannelAlreadyInUse(Exception):
    pass
        
class ValueChange:
    """
    Internal class to control the value of an output device 

    :param OutputDevice output_device:
        The OutputDevice object you wish to change the value of

    :param generator:
        A generator function which yields a 2d list of
        ((value, seconds), *).
        
        The output_device's value will be set for the number of
        seconds.

    :param int n:
        The number of times to repeat the sequence. If None, the
        sequence will repeat forever. 
    
    :param bool wait:
        If True the ValueChange object will block (wait) until
        the sequence has completed.
    """
    def __init__(self, output_device, generator, n, wait):
        self._output_device = output_device
        self._generator = generator
        self._n = n

        self._gen = self._generator()
        
        self._timer = Timer()
        self._running = True
        self._set_value()
        
        while wait and self._running:
            sleep(0.001)
            
    def _set_value(self, timer_obj=None):
        
        try:
            if self._running:
                next_seq = next(self._gen)
                value, seconds = next_seq
        
                self._output_device._write(value)            
                self._timer.init(period=int(seconds * 1000), mode=Timer.ONE_SHOT, callback=self._set_value)
            
        except StopIteration:
            
            self._n = self._n - 1 if self._n is not None else None
            if self._n == 0:
                # its the end, set the value to 0 and stop running
                self._output_device.value = 0
                self._running = False
            else:
                # recreate the generator and start again
                self._gen = self._generator()
                self._set_value()
            
    def stop(self):
        self._running = False
        self._timer.deinit()
        
class OutputDevice:
    """
    Base class for output devices. 
    """   
    def __init__(self, active_high=True, initial_value=False):
        self.active_high = active_high
        self._write(initial_value)
        self._value_changer = None
    
    @property
    def active_high(self):
        """
        Sets or returns the active_high property. If :data:`True`, the 
        :meth:`on` method will set the Pin to HIGH. If :data:`False`, 
        the :meth:`on` method will set the Pin toLOW (the :meth:`off` method 
        always does the opposite).
        """
        return self._active_state

    @active_high.setter
    def active_high(self, value):
        self._active_state = True if value else False
        self._inactive_state = False if value else True
        
    @property
    def value(self):
        """
        Sets or returns a value representing the state of the device. 1 is on, 0 is off.
        """
        return self._read()

    @value.setter
    def value(self, value):
        self._stop_change()
        self._write(value)
        
    def on(self):
        """
        Turns the device on.
        """
        self.value = 1

    def off(self):
        """
        Turns the device off.
        """
        self.value = 0
            
    @property
    def is_active(self):
        """
        Returns :data:`True` if the device is on.
        """
        return bool(self.value)

    def toggle(self):
        """
        If the device is off, turn it on. If it is on, turn it off.
        """
        if self.is_active:
            self.off()
        else:
            self.on()
            
    def blink(self, on_time=1, off_time=None, n=None, wait=False):
        """
        Make the device turn on and off repeatedly.
        
        :param float on_time:
            The length of time in seconds the device will be on. Defaults to 1.

        :param float off_time:
            The length of time in seconds the device will be off. Defaults to 1.

        :param int n:
            The number of times to repeat the blink operation. If None is 
            specified, the device will continue blinking forever. The default
            is None.
        """
        off_time = on_time if off_time is None else off_time
        
        self.off()
        self._start_change(lambda : iter([(1,on_time), (0,off_time)]), n, wait)
            
    def _start_change(self, generator, n, wait):
        self._value_changer = ValueChange(self, generator, n, wait)
    
    def _stop_change(self):
        if self._value_changer is not None:
            self._value_changer.stop()
            self._value_changer = None

    def close(self):
        self.value = 0

class DigitalOutputDevice(OutputDevice):
    def __init__(self, pin, active_high=True, initial_value=False):
        self._pin = Pin(pin, Pin.OUT)
        super().__init__(active_high, initial_value)
        
    def _value_to_state(self, value):
        return int(self._active_state if value else self._inactive_state)
    
    def _state_to_value(self, state):
        return int(bool(state) == self._active_state)
    
    def _read(self):
        return self._state_to_value(self._pin.value())

    def _write(self, value):
        self._pin.value(self._value_to_state(value))
                
    def close(self):
        """
        Closes the device and turns the device off. Once closed, the device
        can no longer be used.
        """
        super().close()
        self._pin = None
        
class DigitalLED(DigitalOutputDevice):
    """
    Represents a simple LED which can be switched on and off.

    :param int pin:
        The pin that the device is connected to.

    :param bool active_high:
        If :data:`True` (the default), the :meth:`on` method will set the Pin
        to HIGH. If :data:`False`, the :meth:`on` method will set the Pin to
        LOW (the :meth:`off` method always does the opposite).

    :param bool initial_value:
        If :data:`False` (the default), the LED will be off initially.  If
        :data:`True`, the LED will be switched on initially.
    """
    pass

DigitalLED.is_lit = DigitalLED.is_active

class Buzzer(DigitalOutputDevice):
    pass

Buzzer.beep = Buzzer.blink

class PWMOutputDevice(OutputDevice):
    
    PIN_TO_PWM_CHANNEL = ["0A","0B","1A","1B","2A","2B","3A","3B","4A","4B","5A","5B","6A","6B","7A","7B","0A","0B","1A","1B","2A","2B","3A","3B","4A","4B","5A","5B","6A","6B"]
    _channels_used = {}
    
    def __init__(self, pin, freq=100, duty_factor=65025, active_high=True, initial_value=False):
        self._check_pwm_channel(pin)
        self._pin_num = pin
        self._duty_factor = duty_factor
        self._pwm = PWM(Pin(pin))
        super().__init__(active_high, initial_value)
        
    def _check_pwm_channel(self, pin_num):
        channel = PWMOutputDevice.PIN_TO_PWM_CHANNEL[pin_num]
        if channel in PWMOutputDevice._channels_used.keys():
            raise PWMChannelAlreadyInUse(
                f"PWM channel {channel} is already in use by pin {PWMOutputDevice._channels_used[channel]}"
                )
        else:
            PWMOutputDevice._channels_used[channel] = pin_num
        
    def _state_to_value(self, state):
        return (state if self.active_high else 1 - state) / self._duty_factor

    def _value_to_state(self, value):
        return int(self._duty_factor * (value if self.active_high else 1 - value))
    
    def _read(self):
        return self._state_to_value(self._pwm.duty_u16())
    
    def _write(self, value):
        self._pwm.duty_u16(self._value_to_state(value))
        
    @property
    def is_active(self):
        """
        Returns :data:`True` if the device is on.
        """
        return self.value != 0
    
    def close(self):
        """
        Closes the device and turns the device off. Once closed, the device
        can no longer be used.
        """
        super().close()
        del PWMOutputDevice._channels_used[
            PWMOutputDevice.PIN_TO_PWM_CHANNEL[self._pin_num]
            ]
        self._pin = None
    
class PWMLED(PWMOutputDevice):
    def __init__(self, pin, active_high=True, initial_value=False):
        self._brightness = 1
        super().__init__(pin=pin,
            active_high=active_high,
            initial_value=initial_value)
        
    @property
    def brightness(self):
        return self._brightness
    
    @brightness.setter
    def brightness(self, value):
        self._brightness = value
        self.value = 1 if self._brightness > 0 else 0
                
    def _write(self, value):
        super()._write(self._brightness * value)
    
    def _read(self):
        return 1 if super()._read() > 0 else 0

    def blink(self, on_time=1, off_time=None, fade_in_time=0, fade_out_time=None, n=None, wait=False, fps=25):
        """
        Make the device turn on and off repeatedly.
        
        :param float on_time:
            The length of time in seconds the device will be on. Defaults to 1.

        :param float off_time:
            The length of time in seconds the device will be off. If `None`, 
            it will be the same as ``on_time``. Defaults to `None`.

        :param float fade_in_time:
            The length of time in seconds to spend fading in. Defaults to 0.

        :param float fade_out_time:
            The length of time in seconds to spend fading out. If `None`,
            it will be the same as ``fade_in_time``. Defaults to `None`.

        :param int n:
            The number of times to repeat the blink operation. If `None`, the 
            device will continue blinking forever. The default is `None`.

        :param int fps:
           The frames per second that will be used to calculate the number of
           steps between off/on states when fading. Defaults to 25.
        """    
        self.off()
        
        off_time = on_time if off_time is None else off_time
        fade_out_time = fade_in_time if fade_out_time is None else fade_out_time
        
        def blink_generator():
            if fade_in_time > 0:
                for s in [
                    (i * (1 / fps) / fade_in_time, 1 / fps)
                    for i in range(int(fps * fade_in_time))
                    ]:
                    yield s
                
            if on_time > 0:
                yield (1, on_time)

            if fade_out_time > 0:
                for s in [
                    (1 - (i * (1 / fps) / fade_out_time), 1 / fps)
                    for i in range(int(fps * fade_out_time))
                    ]:
                    yield s
                
            if off_time > 0:
                 yield (0, off_time)
            
        self._start_change(blink_generator, n, wait)

    def pulse(self, fade_in_time=1, fade_out_time=None, n=None, wait=False, fps=25):
        """
        Make the device pulse on and off repeatedly.
        
        :param float fade_in_time:
            The length of time in seconds the device will take to turn on.
            Defaults to 1.

        :param float fade_out_time:
           The length of time in seconds the device will take to turn off.
           Defaults to 1.
           
        :param int fps:
           The frames per second that will be used to calculate the number of
           steps between off/on states. Defaults to 25.
           
        :param int n:
           The number of times to pulse the LED. If None the LED will pulse
           forever. Defaults to None.
    
        :param bool wait:
           If True the method will block until the LED stops pulsing. If False
           the method will return and the LED is will pulse in the background.
           Defaults to False.
    
        """
        self.blink(on_time=0, off_time=0, fade_in_time=fade_in_time, fade_out_time=fade_out_time, n=n, wait=wait, fps=fps)
    
# factory for returning an LED
def LED(pin, use_pwm=True, active_high=True, initial_value=False):
    """
    Returns an instance of :class:`DigitalLED` or :class:`PWMLED` depending on
    the value of `use_pwm` parameter. 

    ::

        from picozero import LED

        my_pwm_led = LED(1)

        my_digital_led = LED(2, use_pwm=False)

    :param int pin:
        The pin that the device is connected to.

    :param int pin:
        If `use_pwm` is :data:`True` (the default), a :class:`PWMLED` will be
        returned. If `use_pwm` is :data:`False`, a :class:`DigitalLED` will be
        returned. A :class:`PWMLED` can control the brightness of the LED but
        uses 1 PWM channel.

    :param bool active_high:
        If :data:`True` (the default), the :meth:`on` method will set the Pin
        to HIGH. If :data:`False`, the :meth:`on` method will set the Pin to
        LOW (the :meth:`off` method always does the opposite).

    :param bool initial_value:
        If :data:`False` (the default), the device will be off initially.  If
        :data:`True`, the device will be switched on initially.
    """
    if use_pwm:
        return PWMLED(
            pin=pin,
            active_high=active_high,
            initial_value=initial_value)
    else:
        return DigitalLED(
            pin=pin,
            active_high=active_high,
            initial_value=initial_value)

pico_led = LED(25)

class InputDevice:
    """
    Base class for input devices.
    """
    def __init__(self, active_state=None):
        self._active_state = active_state

    @property
    def active_state(self):
        """
        Sets or returns the active state of the device. If :data:`None` (the default),
        the device will return the value that the pin is set to. If
        :data:`True`, the device will return :data:`True` if the pin is
        HIGH. If :data:`False`, the device will return :data:`False` if the
        pin is LOW.
        """
        return self._active_state

    @active_state.setter
    def active_state(self, value):
        self._active_state = True if value else False
        self._inactive_state = False if value else True
        
    @property
    def value(self):
        """
        Returns the current value of the device. This is either :data:`True` 
        or :data:`False` depending on the value of :attr:`active_state`.
        """
        return self._read()

class DigitalInputDevice(InputDevice):
    """
    :param int pin:
        The pin that the device is connected to.

    :param bool pull_up:
        If :data:`True` (the default), the device will be pulled up to
        HIGH. If :data:`False`, the device will be pulled down to LOW.

    :param bool active_state:
        If :data:`True` (the default), the device will return :data:`True`
        if the pin is HIGH. If :data:`False`, the device will return
        :data:`False` if the pin is LOW.

    :param float bounce_time:
        The bounce time for the device. If set, the device will ignore
        any button presses that happen within the bounce time after a
        button release. This is useful to prevent accidental button
        presses from registering as multiple presses.
    """
    def __init__(self, pin, pull_up=False, active_state=None, bounce_time=None):
        super().__init__(active_state)
        self._pin = Pin(
            pin,
            mode=Pin.IN,
            pull=Pin.PULL_UP if pull_up else Pin.PULL_DOWN)
        self._bounce_time = bounce_time
        
        if active_state is None:
            self._active_state = False if pull_up else True
        else:
            self._active_state = active_state
        
        self._state = self._pin.value()
        
        self._when_activated = None
        self._when_deactivated = None
        
        # setup interupt
        self._pin.irq(self._pin_change, Pin.IRQ_RISING | Pin.IRQ_FALLING)
        
    def _state_to_value(self, state):
        return int(bool(state) == self._active_state)
    
    def _read(self):
        return self._state_to_value(self._state)

    def _pin_change(self, p):
        # turn off the interupt
        p.irq(handler=None)
        
        last_state = p.value()
        
        if self._bounce_time is not None:
            # wait for stability
            stop = ticks_ms() + (self._bounce_time * 1000)
            while ticks_ms() < stop:
                # keep checking, reset the stop if the value changes
                if p.value() != last_state:
                    stop = ticks_ms() + self._bounce_time
                    last_state = p.value()
        
        # re-enable the interupt
        p.irq(self._pin_change, Pin.IRQ_RISING | Pin.IRQ_FALLING)
        
        # did the value actually changed? 
        if self._state != last_state:
            # set the state
            self._state = self._pin.value()
            
            # manage call backs
            if self.value and self._when_activated is not None:
                self._when_activated()
            elif not self.value and self._when_deactivated is not None:
                self._when_deactivated()
                    
    @property
    def is_active(self):
        """
        Returns :data:`True` if the device is active.
        """
        return bool(self.value)

    @property
    def is_inactive(self):
        """
        Returns :data:`True` if the device is inactive.
        """
        return not bool(self.value)
    
    @property
    def when_activated(self):
        """
        Returns a :samp:`callback` that will be called when the device is activated.
        """
        return self._when_activated
    
    @when_activated.setter
    def when_activated(self, value):
        self._when_activated = value
        
    @property
    def when_deactivated(self):
        """
        Returns a :samp:`callback` that will be called when the device is deactivated.
        """
        return self._when_deactivated
    
    @when_activated.setter
    def when_deactivated(self, value):
        self._when_deactivated = value
    
    def close(self):
        """
        Closes the device and releases any resources. Once closed, the device
        can no longer be used.
        """
        self._pin.irq(handler=None)
        self._pin = None
        
        
class Switch(DigitalInputDevice):
    """
    :param int pin:
        The pin that the device is connected to.

    :param bool pull_up:
        If :data:`True` (the default), the device will be pulled up to
        HIGH. If :data:`False`, the device will be pulled down to LOW.

    :param float bounce_time:
        The bounce time for the device. If set, the device will ignore
        any button presses that happen within the bounce time after a
        button release. This is useful to prevent accidental button
        presses from registering as multiple presses. Defaults to 0.02 
        seconds.
    """
    def __init__(self, pin, pull_up=True, bounce_time=0.02): 
        super().__init__(pin=pin, pull_up=pull_up, bounce_time=bounce_time)

Switch.is_closed = Switch.is_active
Switch.is_open = Switch.is_inactive
Switch.when_closed = Switch.when_activated
Switch.when_opened = Switch.when_deactivated

class Button(Switch):
    pass

Button.is_pressed = Button.is_active
Button.when_pressed = Button.when_activated
Button.when_released = Button.when_deactivated 


class RGBLED(OutputDevice):
    def __init__(self, red=None, green=None, blue=None, active_high=True,
                 initial_value=(0, 0, 0), pwm=True):
        self._leds = ()
        self._last = initial_value
        LEDClass = PWMLED if pwm else DigitalLED
        self._leds = tuple(
            LEDClass(pin, active_high=active_high)
            for pin in (red, green, blue))
        super().__init__(active_high, initial_value)
        
    def __del__(self):
        if getattr(self, '_leds', None):
            self._stop_blink()
            for led in self._leds:
                led.__del__()
        self._leds = ()
        super().__del__()

    def _write(self, value):
        if type(value) is not tuple:
            value = (value, ) * 3       
        for led, v in zip(self._leds, value):
            led.brightness = v
        
    @property
    def value(self):
        return tuple(led.brightness for led in self._leds)

    @value.setter
    def value(self, value):
        self._stop_change()
        self._write(value)

    @property
    def is_active(self):
        return self.value != (0, 0, 0)

    is_lit = is_active

    def _to_255(self, value):
        return round(value * 255)
    
    def _from_255(self, value):
        return 0 if value == 0 else value / 255
    
    @property
    def color(self):
        return tuple(self._to_255(v) for v in self.value)

    @color.setter
    def color(self, value):
        self.value = tuple(self._from_255(v) for v in value)

    @property
    def red(self):
        return self._to_255(self.value[0])

    @red.setter
    def red(self, value):
        r, g, b = self.value
        self.value = self._from_255(value), g, b

    @property
    def green(self):
        return self._to_255(self.value[1])

    @green.setter
    def green(self, value):
        r, g, b = self.value
        self.value = r, self._from_255(value), b

    @property
    def blue(self):
        return self._to_255(self.value[2])

    @blue.setter
    def blue(self, value):
        r, g, b = self.value
        self.value = r, g, self._from_255(value)

    def on(self):
        self.value = (1, 1, 1)

    def invert(self):
        r, g, b = self.value
        self.value = (1 - r, 1 - g, 1 - b)
        
    def toggle(self):
        if self.value == (0, 0, 0):
            self.value = self._last or (1, 1, 1)
        else:
            self._last = self.value 
            self.value = (0, 0, 0)
            
    def blink(self, on_times=1, fade_times=0, colors=((1, 0, 0), (0, 1, 0), (0, 0, 1)), n=None, wait=False, fps=25):
        
        self.off()
        
        if type(on_times) is not tuple:
            on_times = (on_times, ) * len(colors)
        if type(fade_times) is not tuple:
            fade_times = (fade_times, ) * len(colors)
        # If any value is above zero then treat all as 0-255 values
        if any(v > 1 for v in sum(colors, ())):
            colors = tuple(tuple(self._from_255(v) for v in t) for t in colors)
        
        def blink_generator():
        
            # Define a linear interpolation between
            # off_color and on_color
            
            lerp = lambda t, fade_in, color1, color2: tuple(
                (1 - t) * off + t * on
                if fade_in else
                (1 - t) * on + t * off
                for off, on in zip(color2, color1)
                )
            
            for c in range(len(colors)):
                if fade_times[c] > 0:
                    for i in range(int(fps * fade_times[c])):
                        v = lerp(i * (1 / fps) / fade_times[c], True, colors[(c + 1) % len(colors)], colors[c])
                        t = 1 / fps       
                        yield (v, t)
            
                if on_times[c] > 0:
                    yield (colors[c], on_times[c])
    
        self._start_change(blink_generator, n, wait)
            
    def pulse(self, fade_times=1, colors=((0, 0, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0), (0, 0, 0), (0, 0, 1)), n=None, wait=False, fps=25):
        """
        Make the device fade in and out repeatedly.
        :param float fade_in_times:
            Number of seconds to spend fading in. Defaults to 1.
        :param float fade_out_time:
            Number of seconds to spend fading out. Defaults to 1.
        :type on_color: ~colorzero.Color or tuple
        :param on_color:
            The color to use when the LED is "on". Defaults to white.
        :type off_color: ~colorzero.Color or tuple
        :param off_color:
            The color to use when the LED is "off". Defaults to black.
        :type n: int or None
        :param n:
            Number of times to pulse; :data:`None` (the default) means forever.
        """
        on_times = 0
        self.blink(on_times, fade_times, colors, n, wait, fps)
        
    def cycle(self, fade_times=1, colors=((1, 0, 0), (0, 1, 0), (0, 0, 1)), n=None, wait=False, fps=25):
        """
        Make the device fade in and out repeatedly.
        :param float fade_in_time:
            Number of seconds to spend fading in. Defaults to 1.
        :param float fade_out_time:
            Number of seconds to spend fading out. Defaults to 1.
        :type on_color: ~colorzero.Color or tuple
        :param on_color:
            The color to use when the LED is "on". Defaults to white.
        :type off_color: ~colorzero.Color or tuple
        :param off_color:
            The color to use when the LED is "off". Defaults to black.
        :type n: int or None
        :param n:
            Number of times to pulse; :data:`None` (the default) means forever.
        """
        on_times = 0
        self.blink(on_times, fade_times, colors, n, wait, fps)


class AnalogInputDevice(InputDevice):
    def __init__(self, pin, active_state=True, threshold=0.5):
        super().__init__(active_state)
        self._adc = ADC(pin)
        self._threshold = float(threshold)
        
    def _state_to_value(self, state):
        return (state if self.active_state else 1 - state) / 65535

    def _value_to_state(self, value):
        return int(65535 * (value if self.active_state else 1 - value))
    
    def _read(self):
        return self._state_to_value(self._adc.read_u16())
        
    @property
    def threshold(self):
        return self._threshold

    @threshold.setter
    def threshold(self, value):
        self._threshold = float(value)

    @property
    def is_active(self):
        return self.value > self.threshold

    @property
    def voltage(self):
        return self.value * 3.3
    
    @property
    def percent(self):
        return int(self.value * 100)
    
class Potentiometer(AnalogInputDevice):
    pass

Pot = Potentiometer

def pico_temp_conversion(voltage):
    # Formula for calculating temp from voltage for the onboard temperature sensor
    return 27 - (voltage - 0.706)/0.001721

class TemperatureSensor(AnalogInputDevice):
    def __init__(self, pin, active_state=True, threshold=0.5, conversion=None):
         self._conversion = conversion
         super().__init__(pin, active_state, threshold)
        
    @property
    def temp(self):
        if self._conversion is not None:
            return self._conversion(self.voltage)
        else:
            return None
       
pico_temp_sensor = TemperatureSensor(4, True, 0.5, pico_temp_conversion)
TempSensor = TemperatureSensor
Thermistor = TemperatureSensor

class PWMBuzzer(PWMOutputDevice):
    
    NOTES = {'b0': 31, 'c1': 33, 'c#1': 35, 'd1': 37, 'd#1': 39, 'e1': 41, 'f1': 44, 'f#1': 46, 'g1': 49,'g#1': 52, 'a1': 55,
             'a#1': 58, 'b1': 62, 'c2': 65, 'c#2': 69, 'd2': 73, 'd#2': 78,
    'e2': 82, 'f2': 87, 'f#2': 93, 'g2': 98, 'g#2': 104, 'a2': 110, 'a#2': 117, 'b2': 123,
    'c3': 131, 'c#3': 139, 'd3': 147, 'd#3': 156, 'e3': 165, 'f3': 175, 'f#3': 185, 'g3': 196, 'g#3': 208, 'a3': 220, 'a#3': 233, 'b3': 247,
    'c4': 262, 'c#4': 277, 'd4': 294, 'd#4': 311, 'e4': 330, 'f4': 349, 'f#4': 370, 'g4': 392, 'g#4': 415, 'a4': 440,'a#4': 466,'b4': 494,
    'c5': 523, 'c#5': 554, 'd5': 587, 'd#5': 622, 'e5': 659, 'f5': 698, 'f#5': 740, 'g5': 784, 'g#5': 831, 'a5': 880, 'a#5': 932, 'b5': 988,
    'c6': 1047, 'c#6': 1109, 'd6': 1175, 'd#6': 1245, 'e6': 1319, 'f6': 1397, 'f#6': 1480, 'g6': 1568, 'g#6': 1661, 'a6': 1760, 'a#6': 1865, 'b6': 1976,
    'c7': 2093, 'c#7': 2217, 'd7': 2349, 'd#7': 2489,
    'e7': 2637, 'f7': 2794, 'f#7': 2960, 'g7': 3136, 'g#7': 3322, 'a7': 3520, 'a#7': 3729, 'b7': 3951,
    'c8': 4186, 'c#8': 4435, 'd8': 4699, 'd#8': 4978 }
    
    def __init__(self, pin, freq=440, active_high=True, initial_value=0, volume=0.5, bpm=120, duty_factor=1023):
        self._bpm = bpm
        self._volume = volume
        super().__init__(
            pin, 
            freq=freq, 
            duty_factor=duty_factor, 
            active_high=active_high, 
            initial_value= (freq, volume),
            )
    
    @property
    def bpm(self):
        return self._bpm

    @bpm.setter
    def bpm(self, value):
        self._bpm = value
        
    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = value
        
    @property
    def value(self):
        return tuple(self._pwm.freq(), self.volume)

    @value.setter
    def value(self, value):
        self._stop_change()
        self._write(value)   
           
    def _write(self, value):        
        if value == 0 or value is None or value == '':           
            volume = 0
        else:
            if type(value) is not tuple:
                value = (value, self.volume)
                
            (freq, volume) = value
            freq = self._to_freq(freq)
            
            if freq is not None and freq is not '' and freq !=0:
                self._pwm.freq(freq)
            else:
                volume = 0
                
        super()._write(volume)
                    
    def pitch(self, freq=440, duration=1, volume=1, wait=True):
        if duration is None:
            self.value = (freq, volume)
        else:
            self.off()
            self._start_change(lambda : iter([((freq, volume), duration)]), 1, wait)
        
    def _to_freq(self, freq):
        if freq is not None and freq is not '' and freq != 0: 
            if type(freq) is str:
                return int(self.NOTES[freq])
            elif freq <= 128 and freq > 0: # MIDI
                midi_factor = 2**(1/12)
                return int(440 * midi_factor ** (freq - 69))
            else:
                return freq
        else:
            return None
                
    def to_seconds(self, duration):
        return (duration * 60 / self._bpm) 
                
    def play(self, tune=440, duration=4, volume=1, n=1, wait=True, multiplier=0.9):
        
        if type(tune) is not list: # use note and duration, no generator
            duration = self.to_seconds(duration * multiplier)
            self.pitch(tune, duration, volume, wait)  
        elif type(tune[0]) is not list: # single note don't use a generator
            duration = self.to_seconds(tune[1] * multiplier)
            self.pitch(tune[0], duration, volume, wait) #, volume, multiplier, wait) 
        else: # tune with multiple notes
            def tune_generator():
                for next in tune:
                    note = next[0]
                    if len(next) == 2:
                        duration = self.to_seconds(float(next[1]))
                    if note == '' or note is None:
                        yield ((None, 0), duration)            
                    else:
                        yield ((note, volume), duration * multiplier)
                        yield ((None, 0), duration * (1 - multiplier))

            self.off()
            self._start_change(tune_generator, n, wait)
         
    def _stop(self, timer_obj=None):
        self.off()
                
    def on(self, freq=440, volume=1):
        if freq is not None:
            self.value = (freq, volume)
        
    def __del__(self):
        self.off()
        super().__del__()

PWMBuzzer.beep = PWMBuzzer.blink

def Speaker(pin, use_tones=True, active_high=True, volume=1, initial_value=False, bpm=120):
    if use_tones:
        return PWMBuzzer(pin, freq=440, active_high=active_high, initial_value=volume, bpm=bpm)
    else:
        return Buzzer(pin, active_high=active_high, initial_value=False)
