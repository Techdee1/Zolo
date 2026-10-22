"""Phone-call approval: a lower-assurance channel for customers who cannot use a passkey.

The customer is called, hears the same readback, and approves by typing a Zolo PIN on the keypad.
A voice on its own never approves, and nothing here changes a payment's state: that stays with
the consent module.
"""
