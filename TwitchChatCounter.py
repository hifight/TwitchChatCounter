import requests
import time
import os
import datetime
import webbrowser

import threading

from tkinter import *
from tkinter import filedialog


class TwitchChatGetThread(threading.Thread):
    """
    Chat count getter thread
    Modified version of Twitch-Chat-Downloader from PetterKraabol
    https://github.com/PetterKraabol/Twitch-Chat-Downloader
    """
    def __init__(self, ui, save_dir, video_id):
        threading.Thread.__init__(self)
        self.ui = ui
        self.save_dir = save_dir
        self.video_id = video_id
        self.chat_api_url = 'https://rechat.twitch.tv/rechat-messages'
        self.sorted_list = []
        self.stop_flag = False
        self.daemon = True
        self.start()

    def run(self):
        # Get start and stop time by looking at the 'detail' message from Twitch
        #
        # If you query this API with invalid an invalid timestamp (none or out of range),
        # it will tell you the start and stop timestamp, however, in text format.
        try:
            response = self.request_rechat(0, self.video_id).json()
        except Exception:
            self.ui.add_log("Cannot get data from Twitch API")
            self.ui.thread_finished()
            return

        # Parse response for start and stop
        #
        # The response will look something like this
        # {
        #   "errors": [
        #     {
        #       "status": 400,
        #       "detail": "0 is not between 1469108651 and 1469133795"
        #     }
        #   ]
        # }
        #
        # As the start and stop timestamp is (for some weird reason)
        # in text format, we have to parse the response.
        detail = response['errors'][0]['detail'].split(' ')  # We split the detail string into an array

        # Check if valid video ID
        # If the length is 8, it's (most likely) invalid
        # If the length is 7, it's (most likely) valid
        if len(detail) != 7:
            self.ui.add_log('Video ID is not correct')
            return

        # Start and stop points of full video
        self.original_start = int(detail[4])  # The start timestamp is on index 4
        self.original_stop = int(detail[6])  # while stop has the index 6
        self.full_range = self.original_stop - self.original_start

        # Real start and stop time. Modified this if you don't want a full video
        start = self.original_start
        stop = self.original_stop

        # Create directory if not existed
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

        # Open file
        file = open(self.save_dir + '/' + self.video_id + '.csv', 'w')
        file.write('Timestamp, Count\n')

        # Download messages from timestamps between start and stop.
        timestamp = start
        while timestamp <= stop:

            # Wait for cooldown timer and request new messages from Twitch
            # The API returns the next 30 seconds of messages
            time.sleep(0.5)
            response = self.request_rechat(timestamp, self.video_id).json()
            data = response['data'];

            current_relative_time = timestamp - self.original_start
            relativeTimeStamp = str(datetime.timedelta(seconds=current_relative_time))
            chat_count = len(data)

            # Write to file
            line = relativeTimeStamp + ',' + str(chat_count) + '\n'
            file.write(line)

            self.insert_sorted_list(chat_count, relativeTimeStamp)

            # Add log
            percentage = '{0:.0%}'.format(current_relative_time / self.full_range)
            self.ui.add_log(percentage + ' ' + line)

            # Increase timestamp to get the next 30 seconds of messages in the next loop
            timestamp += 30

            # If stop_flag is True, stop process
            if self.stop_flag:
                break

        self.ui.thread_finished(self.sorted_list)

    def insert_sorted_list(self, chat_count, timestamp):
        for i in range(len(self.sorted_list)):
            if chat_count > self.sorted_list[i]['count']:
                self.sorted_list.insert(i, {'count': chat_count, 'timestamp': timestamp})
                return

        self.sorted_list.append({'count': chat_count, 'timestamp': timestamp})

    def request_rechat(self, start_time, video_id):
        return requests.get(self.create_rechat_get_url(start_time, video_id))

    def create_rechat_get_url(self, start_time, video_id):
        return self.chat_api_url + '?start=' + str(start_time) + '&video_id=v' + video_id

    def stop_thread(self):
        self.stop_flag = True

class TwitchChatCounterUI:

    def __init__(self, parent):
        # Set window title
        parent.title("TwitchChatCounter")
        parent.wm_geometry('500x500')

        self.parent = parent

        self.is_running = False

        # ---------------------------
        # Setup browse frame
        browse_frame = Frame(parent)
        browse_frame.pack(fill=X)

        browse_button = Button(browse_frame, text="Browse", command=self.browse_command)
        browse_button.pack(side=LEFT, padx=5, pady=5)

        self.browse_path_label = Label(browse_frame, anchor=W)
        self.browse_path_label.pack(side=LEFT, fill=X, expand=1, padx=5, pady=5)

        # ---------------------------
        # Setup video id frame
        video_id_frame = Frame(parent)
        video_id_frame.pack(fill=X)

        video_id_label = Label(video_id_frame, text='Video ID:')
        video_id_label.pack(side=LEFT, padx=5, pady=5)

        self.video_id_entry = Entry(video_id_frame)
        self.video_id_entry.pack(side=LEFT, padx=5, pady=5)

        self.start_button = Button(video_id_frame, text="Start", command=self.run_command)
        self.start_button.pack(side=RIGHT, padx=5, pady=5)

        # ---------------------------
        # Setup console frame
        console_frame = Frame(parent)
        console_frame.pack(fill=BOTH, expand=1)

        console_scrollbar = Scrollbar(console_frame, orient=VERTICAL)
        self.console_listbox = Listbox(console_frame, yscrollcommand=console_scrollbar.set)
        self.console_listbox.pack(side=LEFT, expand=1, fill=BOTH, padx=5, pady=5)
        console_scrollbar.config(command=self.console_listbox.yview)
        console_scrollbar.pack(side=RIGHT, fill=Y)

        self.last_selected_index = -1
        self.console_listbox.bind('<<ListboxSelect>>', self.on_select_list)
        self.console_link = {}

    def on_select_list(self, event):
        w = event.widget
        index = int(w.curselection()[0])
        if index == self.last_selected_index:
            if str(index) in self.console_link:
                webbrowser.open(self.console_link[str(index)])

        self.last_selected_index = index


    def browse_command(self):
        self.save_directory = filedialog.askdirectory()
        self.browse_path_label.configure(text=self.save_directory)
        self.add_log("Set save directory to " + self.save_directory)

    def run_command(self):
        if self.is_running == True:
            self.stop_command()
        else:
            self.start_command()

    def start_command(self):
        self.current_video_id = self.video_id_entry.get()
        self.get_thread = TwitchChatGetThread(self, self.save_directory, self.current_video_id)

        self.start_button.configure(text="Stop")
        self.is_running = True

    def stop_command(self):
        self.get_thread.stop_thread()
        self.start_button.configure(text="Start")


    def thread_finished(self, sorted_list):
        self.is_running = False
        self.add_log("Finished!")
        self.start_button.configure(text="Start")

        top_range = min(20, len(sorted_list))
        self.add_log('Top ' + top_range + ' Chat Count')
        for i in range(top_range):
            print(sorted_list[i])
            chat_count = sorted_list[i]['count']
            timestamp = sorted_list[i]['timestamp']
            index = self.add_log(str(i+1) + '. Count=' + str(chat_count) + " timestamp=" + timestamp)

            timestamp_split = timestamp.split(':')
            hour = timestamp_split[0] + 'h'
            minute = timestamp_split[1] + 'm'
            second = timestamp_split[2] + 's'
            self.console_link[str(index)] = 'https://www.twitch.tv/videos/' + self.current_video_id + '?t=' + hour + minute + second

    def add_log(self, text):
        self.console_listbox.insert(END, text)

        # Clear the current selected item
        self.console_listbox.select_clear(self.console_listbox.size() - 2)

        # Select the new item
        self.console_listbox.select_set(END)

        # Set the scrollbar to the end of the listbox
        self.console_listbox.yview(END)

        # Index of added log
        return self.console_listbox.size() - 1

if __name__ == "__main__":
    # Create tkinter root
    root = Tk()

    TwitchChatCounterUI(root)

    root.update_idletasks()
    root.mainloop()