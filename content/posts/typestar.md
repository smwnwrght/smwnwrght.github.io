---
title: "TEXT-A-TYPEWRITER"
date: 2022-04-20
draft: false
description: 'Making a 1995 electric typewriter print out text messages.'
tags: [projects]
url: /typestar
---
Making a 1995 typewriter print out text messages.

# a text-receiving typewriter
Typewriters are simultaneously beautiful, scrawl-replacing and nostalgia-inducing. I wanted to use on to print out SMS messages.

## the build

### choosing the typewriter
In the mid to late 1980s, Casio briefly made a handful of absolutely beautiful machines called *Typestars*.

![Typestar](/images/typestar/manual.png)

The Canon Typestar single-handedly spans the narrow gap between
- **mechanical (and electromechanical) typewriters**, which would be too hard to interface with a SIM card chip, and
- **word processors**, which are completely hideous, bulky objects that died the death they deserved to.

It comes with a cassette of ink, but is equally suited to printing directly onto thermal paper (fax or receipt printer paper).

### how the typewriter works
![Notebook](/images/typestar/circuit.jpeg)

The Typestar has a clever multiplexing situation going on.

The keyboard is connected via two ribbon cables.
- When you press the 'A' button, a connection is made between **wire 1 of ribbon 1** and **wire 1 of ribbon 2**.
- Press 'B' and **wire 1 of ribbon 1** is connected to **wire *2* of ribbon 2**.

And so on as follows, covering every key of the keyboard

```
      RIBBON 2
      1 2 3 4 5 6 7 8 9 10

R 1   a b c d e f g h
I 2   i j k l m n o p
B 3   q r s t u v w x
B 4   y z
O 5   6 5 3 4
N 6   7 8 2   9
~ 7   1
1 8  
```

I found this [teardown video](https://www.youtube.com/watch?v=42fLdTLuYj0) helpful.

### communicating with the typewriter
To emulate this, I used an Arduino to activate transistors, one per wire, allowing current to flow between the wires. This required 2 sets of 8 transistors, one set PNP and the other NPN.

To type an 'A' I need to allow current to flow through two transistors: the one connected to **ribbon 1 wire 1** and **ribbon 2 wire 1**.

![Idea](/images/typestar/idea.jpeg)

### completing the circuit
The full typewriter communication circuit also required
- **some resistors** - not sure why but this seemed to be the only way to get the transistors to work consistently
- **shift registers** to provide more GPIO pins
- **the sim card reader** which is a SIM900 dev board. This connects to the Arduino. There is a standard communications protocol for talking to SIM900 boards
- **a 12V-5V buck converter** - whilst the Arduino can just run off the Typestar's 12V supply, the SIM900 needs 5V

![Circuit](/images/typestar/closeup.jpeg)

### code
The code on the Arduino
- Receives the incoming message
- Cleans it up to generate the text
- Activates transistors in pairs to simulate keyboard button presses
- Presses enter to print the message

## the result
This thing is now mounted to my wall and every so often I decide to write a shopping list on it.

![Typestar](/images/typestar/typestar.jpeg)

# post-script
The medium an artist chooses mediates the communication of an idea. In doing so it has a huge impact on the artwork itself.

In music too, recording and storage technology helps to define the sound of an era. Instruments were chosen that could be heard clearly on a gramophone; album length became defined by the space on an LP, cassette or CD; and while radio pushed track length down to 3 minutes, the number of tracks on an album is increasing to generate more Spotify streams.

So how has technology affected our communication? Until recently you could either write a letter, call someone or see them in real life. SMS and emails were fairly recent additions to communication media but have been pretty much replaced with WhatsApp and DMs. One of the strangest outcomes is internet-era-born Gen Z won't pick up audio calls but prefer to speak by video.

Maybe text-a-typewriter will bring new types of message into my life. Or maybe not.
