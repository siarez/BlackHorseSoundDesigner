# Black Horse Sound Designer User Manual

## Table of Contents

- [Overview](#overview)
- [Basic Workflow](#basic-workflow)
- [Startup and Device Detection](#startup-and-device-detection)
- [General Tab](#general-tab)
  - [Load From Device](#load-from-device)
  - [Read MCU UID](#read-mcu-uid)
  - [Board Name](#board-name)
  - [Factory Reset](#factory-reset)
- [Input Mixer Tab](#input-mixer-tab)
  - [What It Does](#what-it-does)
  - [Controls](#controls)
  - [Typical Stereo Example](#typical-stereo-example)
  - [Sending to the Amp](#sending-to-the-amp)
- [EQ Tab](#eq-tab)
  - [What It Does](#what-it-does-1)
  - [Controls](#controls-1)
  - [Plot](#plot)
  - [Coefficient Display](#coefficient-display)
  - [Sending to the Amp](#sending-to-the-amp-1)
- [Crossover Tab](#crossover-tab)
  - [What It Does](#what-it-does-2)
  - [Per-Channel Output Controls](#per-channel-output-controls)
  - [Filter Sections](#filter-sections)
  - [Plot](#plot-1)
  - [Sending to the Amp](#sending-to-the-amp-2)
- [Sending to Multiple Amps](#sending-to-multiple-amps)
- [Saving and Loading Projects](#saving-and-loading-projects)
  - [Save State](#save-state)
  - [Load State](#load-state)
  - [Load From Device vs Load State](#load-from-device-vs-load-state)
- [Connected Amps Table](#connected-amps-table)
- [Recommended Everyday Workflow](#recommended-everyday-workflow)
- [Troubleshooting](#troubleshooting)
- [Notes](#notes)
- [Quick Reference](#quick-reference)

## Overview

Black Horse Sound Designer is a desktop app for configuring a compatible Black Horse amplifier. In normal mode, the app provides four tabs:

- `General`
- `Input Mixer`
- `EQ`
- `Crossover`

You can use the app to:

- detect connected amps
- name each amp
- read settings back from an amp
- create and edit mixer, EQ, and crossover settings
- send settings to one or more connected amps
- save a project to disk and load it later
- restore an amp to factory defaults

## Basic Workflow

A typical workflow is:

1. Connect your amp by USB.
2. Open the app.
3. Check the `General` tab to confirm the amp appears.
4. Make changes in `Input Mixer`, `EQ`, and `Crossover`.
5. Send settings to the amp from each tab as needed.
6. Optionally save the current project to a file.

## Startup and Device Detection

When the app opens, it automatically looks for connected amps.

In the `General` tab you will see:

- a `Connected Amps` table
- the currently selected amp in the `Load From Device` drop-down
- the selected amp’s UID and board name

If more than one amp is connected:

- each amp appears in the device list
- you can choose which amp to load from in `General`
- send buttons on other tabs will show target selectors so you can choose which amp(s) receive the settings

If only one amp is connected:

- that amp is selected automatically

## General Tab

The `General` tab is for device-level actions.

### Load From Device

Use `Load From Device` to read settings from the selected amp and populate the app UI.

This updates the tabs with the amp’s saved settings. It does not immediately send anything back to the amp.

Use this when:

- you want to inspect the current configuration on a device
- you want to start editing from the amp’s saved state instead of from the current app state

### Read MCU UID

Use `Read MCU UID` to read the selected amp’s unique hardware ID.

You can use `Copy` to copy the UID to the clipboard.

### Board Name

You can assign a user-friendly name to each amp.

To do this:

1. Type a name in the board name field.
2. Click `Save Name To Device`.

Rules:

- maximum length: 25 characters
- printable ASCII only

Once saved, the name is shown throughout the app when identifying that amp.

### Factory Reset

`Factory Reset` restores the selected amp to a known default state.

It performs these actions:

- erases saved settings on the amp
- writes the default TAS3251 settings
- writes the default ES9821 settings

Use this when:

- an amp is in a bad or unknown configuration state
- you want to return a unit to its default baseline

## Input Mixer Tab

The `Input Mixer` tab controls how the two input channels are mixed into the two output paths.

### What It Does

It defines a 2×2 gain matrix:

- `A_out = In1 × (In1 to A) + In2 × (In2 to A)`
- `B_out = In1 × (In1 to B) + In2 × (In2 to B)`

This lets you create behaviors such as:

- normal stereo routing
- mono summing
- cross-routing
- custom blends between inputs and outputs

### Controls

You can set four gains:

- `In1 to A`
- `In2 to A`
- `In1 to B`
- `In2 to B`

The tab also shows:

- hex coefficient values on the left
- effective gains in dB on the right

### Typical Stereo Example

For standard stereo operation:

- `In1 to A = 1.0`
- `In2 to A = 0.0`
- `In1 to B = 0.0`
- `In2 to B = 1.0`

### Sending to the Amp

Click `Send Input Mixer to Device` to send the current mixer settings to the selected amp(s).

## EQ Tab

The `EQ` tab lets you build a cascade of parametric filter sections.

### What It Does

You can configure up to 14 user EQ sections. Each row is one filter.

The plot shows the overall cascade response.

The panel on the left shows coefficient values for the current design.

### Controls

For each row, you can set:

- filter `Type`
- center/cutoff frequency `f₀`
- `Q`
- `Gain`

Available filter types depend on the app’s filter library and may include things like:

- all-pass
- peaking EQ
- low shelf
- high shelf
- other standard biquad shapes

### Plot

The plot shows the overall EQ response across frequency.

This helps you verify:

- tonal shaping
- combined boost/cut
- filter overlap

### Coefficient Display

The left panel can show:

- designed coefficients
- 2’s complement hex values

These are mainly for reference and verification.

### Sending to the Amp

Click `Send EQ to Device` to send the current EQ settings to the selected amp(s).

## Crossover Tab

The `Crossover` tab controls the output crossover for Channel A and Channel B.

### What It Does

This tab defines the filter chains, delays, gains, polarity, and DAC attenuation for the two output channels.

It also shows:

- a plot of Channel A
- a plot of Channel B
- the electrical sum

### Per-Channel Output Controls

For each channel, you can adjust:

- `Invert polarity`
- `DAC -6 dB`
- `Delay`
- `Gain`

#### Invert Polarity

Flips output polarity for that channel.

#### DAC -6 dB

Applies a 6 dB analog DAC attenuation for that channel.

This is useful for:

- very sensitive tweeters
- very sensitive drivers
- reducing audible background hiss

#### Delay

Applies channel delay in samples.

The app also shows the approximate acoustic distance equivalent.

#### Gain

Applies output gain for that channel.

The app also shows the approximate linear gain multiplier.

### Filter Sections

Each channel has 5 crossover/filter rows.

For each row you can configure:

- `Mode`
- `Topology`
- `f₀`
- `Q`
- `Ripple / dB`

The enabled fields depend on the selected filter mode and topology.

### Plot

The crossover plot helps you verify:

- each channel’s response
- phase-related summation behavior
- the electrical sum between Channel A and Channel B

### Sending to the Amp

Click `Send Crossover to Device` to send the current crossover settings to the selected amp(s).

## Sending to Multiple Amps

If multiple amps are connected, send-capable tabs may show amp selectors near the send button.

Behavior:

- you can choose which amp(s) receive the settings
- if only one amp is connected, the target is shown automatically
- if no target is selected, the send action is disabled

This allows you to:

- program one amp at a time
- program several amps with the same settings

## Saving and Loading Projects

Use the `File` menu or toolbar to save and load project files.

### Save State

`Save State` stores the current app settings to a file on your computer.

This is useful for:

- backups
- sharing settings
- versioning your work
- restoring a known tuning later

### Load State

`Load State` loads a previously saved project file into the app UI.

This does not automatically send settings to the amp. After loading, use the send buttons on the relevant tabs.

### Load From Device vs Load State

These are different:

- `Load State` reads a project file from your computer
- `Load From Device` reads saved settings from the selected amp

## Connected Amps Table

The `Connected Amps` table in `General` shows connected devices and their identity.

Typical columns include:

- name
- UID
- USB port
- status

This is useful when:

- you have multiple amps connected
- you want to confirm which device you are about to program
- you want to identify a device by board name instead of by USB path

## Recommended Everyday Workflow

For a single amp:

1. Connect the amp.
2. Confirm it appears in `General`.
3. Optionally use `Load From Device`.
4. Adjust `Input Mixer`.
5. Send mixer settings.
6. Adjust `EQ`.
7. Send EQ settings.
8. Adjust `Crossover`.
9. Send crossover settings.
10. Save the project to disk.

For multiple amps:

1. Connect all amps.
2. Confirm they appear in `General`.
3. Give each amp a clear board name.
4. Use the send target selectors on each tab to choose which amp(s) to update.

## Troubleshooting

### The amp does not appear

Check:

- USB cable
- power to the amp
- that the firmware is installed correctly
- that the amp appears in your operating system as a USB serial device

### The wrong amp is selected

Go to `General` and choose the correct amp from the source drop-down. Saving a board name makes this much easier.

## Notes

- The app does not automatically send every UI change to the amp. Use the send button on each tab.
- Loading a state, whether from disk or from a device, updates the UI first. Sending is still a separate step.
- Board names are stored on the amp and help identify devices in multi-amp setups.

## Quick Reference

### General

- `Load From Device`: read settings from the selected amp into the UI
- `Read MCU UID`: read hardware unique ID
- `Save Name To Device`: store a board name
- `Factory Reset`: erase saved settings and restore default device settings

### Input Mixer

- set the 2×2 input-to-output mix matrix
- send with `Send Input Mixer to Device`

### EQ

- configure up to 14 EQ sections
- inspect response in the plot
- send with `Send EQ to Device`

### Crossover

- configure Channel A and Channel B crossovers
- set polarity, DAC attenuation, delay, and gain
- inspect channel and summed responses
- send with `Send Crossover to Device`
