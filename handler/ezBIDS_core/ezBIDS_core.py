#!/usr/bin/env python3

"""
This code represents ezBIDS's attempt to determine BIDS information (subject/session mapping,
datatype, suffix, entity labels [acq, run, dir, etc]) based on dcm2niix output.
This information is then displayed in the ezBIDS UI, where users can make
edits/modifications as they see fit, before finalizing their data into a BIDS-compliant dataset.

Flake8 is used for linting, which highlights sytax and style issues as defined by the PEP guide. Arguements include:
    --max-line-length=125
    --ignore=E722,W503

@author: dlevitas
"""

from __future__ import division
import os
import re
import sys
import json
import yaml
import time
import numpy as np
import pandas as pd
import nibabel as nib
from math import floor
from datetime import date
from natsort import natsorted
from operator import itemgetter
from urllib.request import urlopen
from pathlib import Path

DATA_DIR = sys.argv[1]

PROJECT_DIR = Path(__file__).resolve().parents[2]
BIDS_SCHEMA_DIR = PROJECT_DIR / Path("bids-specification/src/schema")

datatypes_yaml = yaml.load(open(BIDS_SCHEMA_DIR / Path("objects/datatypes.yaml")), Loader=yaml.FullLoader)
entities_yaml = yaml.load(open(BIDS_SCHEMA_DIR / Path("objects/entities.yaml")), Loader=yaml.FullLoader)
suffixes_yaml = yaml.load(open(BIDS_SCHEMA_DIR / Path("objects/suffixes.yaml")), Loader=yaml.FullLoader)
dataset_description_yaml = yaml.load(open(BIDS_SCHEMA_DIR / Path("rules/dataset_metadata.yaml")),
                                     Loader=yaml.FullLoader)
datatype_suffix_rules = str(BIDS_SCHEMA_DIR / Path("rules/datatypes"))
entity_ordering_file = str(BIDS_SCHEMA_DIR / Path("rules/entities.yaml"))

cog_atlas_url = "http://cognitiveatlas.org/api/v-alpha/task"

accepted_datatypes = ["anat", "dwi", "fmap", "func", "perf", "pet"]  # Will add others later

bids_compliant = pd.read_csv(f"{DATA_DIR}/bids_compliant.log", header=None).iloc[1][0]

start_time = time.time()
analyzer_dir = os.getcwd()

today_date = date.today().strftime("%Y-%m-%d")

os.chdir(DATA_DIR)

# Functions


def set_IntendedFor_B0FieldIdentifier_B0FieldSource(dataset_list_unique_series, bids_compliant):
    if bids_compliant == "yes":
        for index, unique_dic in enumerate(dataset_list_unique_series):
            json_path = unique_dic["json_path"]

            json_data = open(json_path)
            json_data = json.load(json_data, strict=False)

            if "IntendedFor" in json_data:
                IntendedFor_indices = []
                IntendedFor = json_data["IntendedFor"]
                for i in IntendedFor:
                    IntendedFor_items = [[x["nifti_path"], x["series_idx"]] for x in dataset_list_unique_series]
                    IntendedFor_items = [x for x in IntendedFor_items if i in x[0]]

                    for IntendedFor_item in IntendedFor_items:
                        IntendedFor_indices.append(IntendedFor_item[1])

                unique_dic["IntendedFor"] = IntendedFor_indices

            if "B0FieldIdentifier" in json_data:
                unique_dic["B0FieldIdentifier"] = json_data["B0FieldIdentifier"]
                if isinstance(unique_dic["B0FieldIdentifier"], str):
                    unique_dic["B0FieldIdentifier"] = [unique_dic["B0FieldIdentifier"]]
            if "B0FieldSource" in json_data:
                unique_dic["B0FieldSource"] = json_data["B0FieldSource"]
                if isinstance(unique_dic["B0FieldSource"], str):
                    unique_dic["B0FieldSource"] = [unique_dic["B0FieldSource"]]

    return dataset_list_unique_series


def generate_readme(DATA_DIR, bids_compliant):

    if bids_compliant == "yes":
        bids_root_dir = pd.read_csv(f"{DATA_DIR}/bids_compliant.log", header=None).iloc[0][0]
        try:
            with open(f"{bids_root_dir}/README") as f:
                lines = f.readlines()
        except:
            lines = []
    else:
        lines = [
            "This data was converted using ezBIDS (https://brainlife.io/ezbids/)."
            "Additional information regarding this dataset can be entered in this file."
        ]

    readme = "\n".join(lines)

    return readme


def generate_dataset_description(DATA_DIR, bids_compliant):
    """
    Creates a template dataset_description file with relevant information study-level information.

    Parameters
    ----------
    DATA_DIR : string
        Root-level directory where uploaded data is stored and assessed.
    bids_compliant: string
        "yes" or "no". Specifies whether the uploaded data is already BIDS-compliant. Can occur when users
        want to have their task event files converted to events.tsv format and/or send their data to brainlife.io
        or OpenNeuro without having to go through the command line terminal.

    Returns
    -------
    dataset_description_dic: dictionary
        Dataset description information
    """
    dataset_description_dic = {}
    for field in dataset_description_yaml["dataset_description"]["fields"]:
        if "GeneratedBy" not in field:
            dataset_description_dic[field] = ""

    if bids_compliant == "yes":
        bids_root_dir = pd.read_csv(f"{DATA_DIR}/bids_compliant.log", header=None).iloc[0][0]
        dataset_description = open(f"{bids_root_dir}/dataset_description.json")
        dataset_description = json.load(dataset_description, strict=False)

        for field in dataset_description:
            if field in dataset_description_dic.keys() and "GeneratedBy" not in field:
                dataset_description_dic[field] = dataset_description[field]

    dataset_description_dic["GeneratedBy"] = [
        {
            "Name": "ezBIDS",
            "Version": "n/a",
            "Description": "ezBIDS is a web-based tool for converting neuroimaging datasets to BIDS, requiring"
                           " neither coding nor knowledge of the BIDS specification",
            "CodeURL": "https://brainlife.io/ezbids/",
            "Container": {
                "Type": "n/a",
                "Tag": "n/a"
            }
        }
    ]

    dataset_description_dic["SourceDatasets"] = [
        {
            "DOI": "n/a",
            "URL": "https://brainlife.io/ezbids/",
            "Version": "n/a"
        }
    ]

    # Explicit checks
    if dataset_description_dic["Name"] == "":
        dataset_description_dic["Name"] = "Untitled"

    if dataset_description_dic["BIDSVersion"] == "":
        dataset_description_dic["BIDSVersion"] = "1.8.0"

    if dataset_description_dic["DatasetType"] == "":
        dataset_description_dic["DatasetType"] = "raw"

    return dataset_description_dic


def generate_participants_columns(DATA_DIR, bids_compliant):
    """
    Sets standard column information for the participants.tsv (and .json) files

    Parameters
    ----------
    DATA_DIR : string
        Root-level directory where uploaded data is stored and assessed.
    bids_compliant: string
        "yes" or "no". Specifies whether the uploaded data is already BIDS-compliant. Can occur when users
        want to have their task event files converted to events.tsv format and/or send their data to brainlife.io
        or OpenNeuro without having to go through the command line terminal.

    Returns
    -------
    participants_column_info: dictionary
        Column information for the participants.tsv (and .json) files
    """
    bids_root_dir = pd.read_csv(f"{DATA_DIR}/bids_compliant.log", header=None).iloc[0][0]

    if bids_compliant == "yes" and os.path.isfile(f"{bids_root_dir}/participants.json"):
        participants_column_info = open(f"{bids_root_dir}/participants.json")
        participants_column_info = json.load(participants_column_info, strict=False)
    else:
        participants_column_info = {
            "sex": {
                "LongName": "gender",
                "Description": "generic gender field",
                "Levels": {
                    "M": "male",
                    "F": "female"
                }
            },
            "age": {
                "LongName": "age",
                "Units": "years"
            }
        }
    return participants_column_info


def find_cog_atlas_tasks(url):
    """
    Generates a list of all possible task names from the Cognitive Atlas API
    task url.

    Parameters
    ----------

    url : string
        web url of the Cognitive Atlas API task page.

    Returns
    -------
    tasks : list
        list of all possible task names. Each task name has spaces, "task", and
        "test" removed, to make it easier to search the SeriesDescription
        fields for a matching task name.
    """
    url_contents = urlopen(url)
    data = json.load(url_contents)
    # Remove non-alphanumeric terms and "task", "test" substrings
    tasks = [re.sub("[^A-Za-z0-9]+", "", re.split(" task| test", x["name"])[0]).lower() for x in data]
    # Remove empty task name terms and ones under 2 characters (b/c hard to detect in SeriesDescription)
    tasks = [x for x in tasks if len(x) > 2]
    tasks = sorted(tasks, key=str.casefold)  # sort alphabetically, but ignore case

    return tasks


def correct_pe(pe_direction, ornt):
    """
    Takes phase encoding direction and image orientation to correct
    pe_direction if need be. This correction occurs if pe_direction
    is in "xyz" format instead of "ijk".

    Function is based on https://github.com/nipreps/fmriprep/issues/2341 and
    code derived from Chris Markiewicz and Mathias Goncalves.

    Parameters
    ----------
    pe_direction : string
        Value from PhaseEncodingDirection in acquisition json file generated
        by dcm2niix
    ornt: string
        Value of "".join(nib.aff2axcodes(nii_img.affine)), where "nii_img" is
        is the acquisition NIFTI file generated by dcm2niix

    Returns
    -------
    proper_pe_direction: string
        pe_direction, in "ijk" format
    """
    # axes = (("R", "L"), ("A", "P"), ("S", "I"))
    proper_ax_idcs = {"i": 0, "j": 1, "k": 2}

    # pe_direction is ijk (no correction necessary)
    if any(x in pe_direction for x in ["i", "i-", "j", "j-", "k", "k"]):
        proper_pe_direction = pe_direction

    # pe_direction xyz (correction required)
    else:
        improper_ax_idcs = {"x": 0, "y": 1, "z": 2}
        axcode = ornt[improper_ax_idcs[pe_direction[0]]]
        axcode_index = improper_ax_idcs[pe_direction[0]]
        inv = pe_direction[1:] == "-"

        if pe_direction[0] == "x":
            if "L" in axcode:
                inv = not inv
        elif pe_direction[0] == "y":
            if "P" in axcode:
                inv = not inv
        elif pe_direction[0] == "z":
            if "I" in axcode:
                inv = not inv
        else:
            ValueError("pe_direction does not contain letter i, j, k, x, y, or z")

        if inv:
            polarity = "-"
        else:
            polarity = ""

        proper_pe_direction = [key for key, value in proper_ax_idcs.items()
                               if value == axcode_index][0] + polarity

    return proper_pe_direction


def determine_direction(pe_direction, ornt):
    """
    Takes [corrected] pe_direction and image orientation to determine "_dir-" entity label,
    which is required or highly recommended for specific acquisitions.

    Based on https://github.com/nipreps/fmriprep/issues/2341 and code derived
    from Chris Markiewicz and Mathias Goncalves.

    Parameters
    ----------
    pe_direction : string
        Value from PhaseEncodingDirection in acquisition json file generated
        by dcm2niix
    ornt: string
        Value of "".join(nib.aff2axcodes(nii_img.affine)), where "nii_img" is
        is the acquisition NIFTI file generated by dcm2niix

    Returns
    -------
    direction: string
        direction for BIDS "_dir-" entity label
    """
    axes = (("R", "L"), ("A", "P"), ("S", "I"))
    ax_idcs = {"i": 0, "j": 1, "k": 2}
    axcode = ornt[ax_idcs[pe_direction[0]]]
    inv = pe_direction[1:] == "-"

    if pe_direction[0] == "i":
        if "L" in axcode:
            inv = not inv
    elif pe_direction[0] == "j":
        if "P" in axcode:
            inv = not inv
    elif pe_direction[0] == "k":
        if "I" in axcode:
            inv = not inv

    for ax in axes:
        for flip in (ax, ax[::-1]):
            if flip[not inv].startswith(axcode):
                direction = "".join(flip)

    return direction


def modify_uploaded_dataset_list(uploaded_json_list):
    """
    Filters the list of json files generated by preprocess.sh to ensure that
    the json files are derived from dcm2niix, and that they contain
    corresponding nifti (and bval/bvec) files. Additionally, Phillips PAR/REC
    files are removed, as they cannot be handled by ezBIDS. If these conditions
    are satisfied, all files are added to a modified dir_list.

    Parameters
    ----------
    uploaded_json_list : list
        list of json files generated from preprocess.sh

    Returns
    -------
    uploaded_files_list: list
        all files (i.e json, nifti, bval/bvec) from uploaded dataset
    """
    uploaded_files_list = []

    # Remove Philips proprietary files in uploaded_json_list if they exist
    uploaded_json_list = natsorted([json for json in uploaded_json_list
                                    if "parrec" not in json.lower()
                                    and "finalized.json" not in json
                                    and "ezBIDS_core.json" not in json]
                                   )

    # Parse json files
    for json_file in uploaded_json_list:
        try:
            json_data = open(json_file)
            json_data = json.load(json_data, strict=False)

            # Only want json files with corresponding nifti (and bval/bvec) and if the files come from dcm2niix
            if ("ConversionSoftware" in json_data and ("dcm2niix" in json_data["ConversionSoftware"]
                                                       or "pypet2bids" in json_data["ConversionSoftware"])):
                json_dir = os.path.dirname(json_file)
                grouped_files = [
                    json_dir + "/" + x for x in os.listdir(json_dir)
                    if os.path.basename(json_file)[:-4] in x
                ]
                # Check that both .nii.gz and .nii aren't in the same group. Redundant, so remove .nii file if found
                if len([x for x in grouped_files if ".nii" in x]) == 2:
                    grouped_files = [x for x in grouped_files if x[-4:] != ".nii"]

                # If json comes with imaging data (NIfTI, bval/bvec) add it to list for processing
                if len(grouped_files) > 1:
                    uploaded_files_list.append(grouped_files)
                data_type = ""
            else:
                data_type = "exclude"
                print(
                    f"{json_file} was not generated from dcm2niix or pypet2bids. "
                    " ezBIDS requires NIfTI/JSON file provenance to be from one "
                    "of these two, thus this will not be converted by ezBIDS."
                )
        except:
            data_type = "exclude"
            print(
                f"{json_file} has improper JSON syntax, possibly because "
                "uploaded data was converted by older dcm2niix version. "
                "Will not be converted by ezBIDS."
            )

    # Flatten uploaded_dataset_list
    uploaded_files_list = [file for sublist in uploaded_files_list for file in sublist]

    return uploaded_files_list, data_type


def generate_dataset_list(uploaded_files_list, data_type):
    """
    Takes list of nifti, json, (and bval/bvec) files generated from dcm2niix
    to create a list of info directories for each uploaded acquisition, where
    each directory contains metadata and other dicom header information to
    help ezBIDS determine the identify of acquisitions, and to determine other
    BIDS-related information (e.g. entity labels).

    Parameters
    ----------
    uploaded_files_list : list
        List of nifti, json, and bval/bvec files generated from dcm2niix. The
        list of files is generated from preprocess.sh

    data_type: str
        Specifies whether the uplaoded data (if NIfTI/JSON) was converted by dcm2niix/pypet2bids.
        If not, this value becomes "exclude", otherwise set it "".

    Returns
    -------
    dataset_list : list
        List of dictionaries containing pertinent and unique information about
        the data, primarily coming from the metadata in the json files
    """
    # Create list for appending dictionaries to
    dataset_list = []

    # Get separate nifti and json (i.e. sidecar) lists
    json_list = [x for x in uploaded_files_list if ".json" in x]
    nifti_list = [
        x for x in uploaded_files_list if ".nii.gz" in x
        or ".bval" in x
        or ".bvec" in x
    ]

    print("Determining unique acquisitions in dataset")
    print("------------------------------------------")
    for json_file in json_list:
        json_data = open(json_file)
        json_data = json.load(json_data, strict=False)
        print(f"JSON file: {json_file}")

        corresponding_nifti = [
            x for x in nifti_list if json_file[:-4] in x
            if ".nii" in x
        ][0]

        # Phase encoding direction info
        if "PhaseEncodingDirection" in json_data:
            pe_direction = json_data["PhaseEncodingDirection"]
        else:
            pe_direction = None

        try:
            ornt = nib.aff2axcodes(nib.load(corresponding_nifti).affine)
            ornt = "".join(ornt)
        except:
            ornt = None

        if pe_direction is not None and ornt is not None:
            proper_pe_direction = correct_pe(pe_direction, ornt)
            ped = determine_direction(proper_pe_direction, ornt)
        else:
            ped = ""

        # Nifti (and bval/bvec) file(s) associated with specific json file
        nifti_paths_for_json = [x for x in nifti_list if json_file[:-4] in x and ".json" not in x]

        # Find nifti file size
        filesize = os.stat(nifti_paths_for_json[0]).st_size

        # Find StudyID from json
        if "StudyID" in json_data:
            study_id = json_data["StudyID"]
        else:
            study_id = ""

        """
        Find subject_id from json, since some files contain neither
        PatientName nor PatientID
        """
        if "PatientName" in json_data:
            patient_name = json_data["PatientName"]
        else:
            patient_name = "n/a"

        if "PatientID" in json_data:
            patient_id = json_data["PatientID"]
        else:
            patient_id = "n/a"

        # Find PatientBirthDate
        if "PatientBirthDate" in json_data:
            patient_birth_date = json_data["PatientBirthDate"].replace("-", "")
        else:
            patient_birth_date = "00000000"

        # Find PatientSex
        patient_sex = "n/a"
        if "PatientSex" in json_data:
            if json_data["PatientSex"] in ["M", "F"]:
                patient_sex = json_data["PatientSex"]

        # Find PatientAge
        if "PatientAge" in json_data:
            patient_age = json_data["PatientAge"]
        else:
            patient_age = "n/a"

        """
        Metadata may contain PatientBirthDate and/or PatientAge. Check either
        to see if one truly provides accurate age information.
        """
        age = "n/a"
        if "PatientAge" in json_data:
            patient_age = json_data["PatientAge"]
            if not patient_age.isalnum():  # if true, is alphanumeric, so not age
                try:
                    # if age is over 100, probably made up
                    if (isinstance(patient_age, int) or isinstance(patient_age, float)) and int(patient_age) < 100:
                        age = patient_age
                except:
                    pass

        if age == "n/a" and "PatientBirthDate" in json_data:
            patient_birth_date = json_data["PatientBirthDate"]  # ISO 8601 "YYYY-MM-DD"
            try:
                age = int(today_date.split("-")[0]) - int(patient_birth_date.split("-")[0])
                - ((int(today_date.split("-")[1]), int(today_date.split("-")[2]))
                    < (int(patient_birth_date.split("-")[2]), int(patient_birth_date.split("-")[2])))
            except:
                pass

        """
        Select subject (and session, if applicable) IDs to display.
        Subject ID precedence order if explicit subject ID is not found: PatientName > PatientID
        """
        sub_search_terms = ["subject", "subj", "sub"]
        ses_search_terms = ["session", "sess", "ses"]

        subject = "n/a"
        for value in [json_file, patient_name, patient_id]:
            for sub_term in sub_search_terms:
                if sub_term in value.lower():
                    item = value.lower().split(sub_term)[-1][0]  # what character comes right after "sub"
                    if item.isalpha() is False and item.isnumeric() is False:
                        subject = re.split('[^a-zA-Z0-9]', value.lower().split(f"{sub_term}{item}")[-1])[0]
                    else:
                        subject = re.split('[^a-zA-Z0-9]', value.lower().split(f"{sub_term}")[-1])[0]
                    break

        if subject == "n/a":
            potential_ID_fields = [patient_name, patient_id]
            for potential_id in potential_ID_fields:
                if potential_id != "n/a":
                    subject = potential_id
                    break

        if subject == "n/a":
            directory_struct = [x for x in json_file.split("/") if ".json" not in x]
            subject = directory_struct[-1]  # Assume folder data found in is the subject ID

        session = ""
        for value in [json_file, patient_name, patient_id]:
            for ses_term in ses_search_terms:
                if ses_term in value.lower():
                    item = value.lower().split(ses_term)[-1][0]  # what character comes right after "sub"
                    if item.isalpha() is False and item.isnumeric() is False:
                        session = re.split('[^a-zA-Z0-9]', value.lower().split(f"{ses_term}{item}")[-1])[0]
                    else:
                        session = re.split('[^a-zA-Z0-9]', value.lower().split(f"{ses_term}")[-1])[0]
                    break

        # Remove non-alphanumeric characters from subject (and session) ID(s)
        subject = re.sub("[^A-Za-z0-9]+", "", subject)
        session = re.sub("[^A-Za-z0-9]+", "", session)

        # Find Acquisition Date & Time
        if "AcquisitionDateTime" in json_data:
            acquisition_date_time = json_data["AcquisitionDateTime"]
            acquisition_date = json_data["AcquisitionDateTime"].split("T")[0]
            acquisition_time = json_data["AcquisitionDateTime"].split("T")[-1]
        else:
            acquisition_date_time = "0000-00-00T00:00:00.000000"
            acquisition_date = "0000-00-00"
            acquisition_time = "00:00:00.000000"

        if "AcquisitionTime" in json_data and acquisition_time == "00:00:00.000000":
            acquisition_time = json_data["AcquisitionTime"]

        # Find TimeZero
        if "TimeZero" in json_data and json_data.get("ScanStart", None) == 0:
            acquisition_time = json_data["TimeZero"]

        # Find RepetitionTime
        if "RepetitionTime" in json_data:
            repetition_time = json_data["RepetitionTime"]
        else:
            repetition_time = 0

        # Find EchoNumber
        if "EchoNumber" in json_data:
            echo_number = json_data["EchoNumber"]
        else:
            echo_number = None

        # Find EchoTime
        if "EchoTime" in json_data:
            echo_time = json_data["EchoTime"] * 1000
        else:
            echo_time = 0

        # Get the nibabel nifti image info
        image = nib.load(json_file[:-4] + "nii.gz")

        # if image.get_data_dtype() == [('R', 'u1'), ('G', 'u1'), ('B', 'u1')]:
        if image.get_data_dtype() in ["<i2", "<u2", "<f4", "int16", "uint16"]:
            valid_image = True
        else:
            valid_image = False

        # Find how many volumes are in corresponding nifti file
        try:
            volume_count = image.shape[3]
        except:
            volume_count = 1

        # Find SeriesNumber
        if "SeriesNumber" in json_data:
            series_number = json_data["SeriesNumber"]
        else:
            series_number = 0

        # Modified SeriesNumber, which zero pads integers < 10. Helpful for sorting purposes
        if series_number < 10:
            mod_series_number = '0' + str(series_number)
        else:
            mod_series_number = str(series_number)

        # Find SeriesDescription
        if "SeriesDescription" in json_data:
            series_description = json_data["SeriesDescription"]
            descriptor = "SeriesDescription"
        else:
            series_description = "n/a"
            descriptor = "ProtocolName"

        # Find ProtocolName
        if "ProtocolName" in json_data:
            protocol_name = json_data["ProtocolName"]
        else:
            protocol_name = "n/a"

        # Find ImageType
        if "ImageType" in json_data:
            image_type = json_data["ImageType"]
        else:
            image_type = []

        # Find ImageModality
        if "Modality" in json_data:
            modality = json_data["Modality"]
        else:
            # assume MR
            modality = "MR"

        # Relative paths of json and nifti files (per SeriesNumber)
        paths = natsorted(nifti_paths_for_json + [json_file])

        # Organize all from individual SeriesNumber in dictionary
        acquisition_info_directory = {
            "StudyID": study_id,
            "PatientName": patient_name,
            "PatientID": patient_id,
            "PatientBirthDate": patient_birth_date,
            "PatientSex": patient_sex,
            "PatientAge": age,
            "subject": subject,
            "session": session,
            "SeriesNumber": series_number,
            "ModifiedSeriesNumber": mod_series_number,
            "AcquisitionDateTime": acquisition_date_time,
            "AcquisitionDate": acquisition_date,
            "AcquisitionTime": acquisition_time,
            "SeriesDescription": series_description,
            "ProtocolName": protocol_name,
            "descriptor": descriptor,
            "Modality": modality,
            "ImageType": image_type,
            "RepetitionTime": repetition_time,
            "EchoNumber": echo_number,
            "EchoTime": echo_time,
            "datatype": "",
            "suffix": "",
            "subject_idx": 0,
            "session_idx": 0,
            "series_idx": 0,
            "direction": ped,
            "exclude": False,
            "filesize": filesize,
            "NumVolumes": volume_count,
            "orientation": ornt,
            "forType": "",
            "error": None,
            "IntendedFor": None,
            "B0FieldIdentifier": None,
            "B0FieldSource": None,
            "section_id": 1,
            "message": None,
            "type": data_type,
            "nifti_path": [x for x in nifti_paths_for_json if ".nii.gz" in x][0],
            "nibabel_image": image,
            "valid_image": valid_image,
            "json_path": json_file,
            "paths": paths,
            "headers": "",
            "sidecar": json_data
        }
        dataset_list.append(acquisition_info_directory)

    # Sort dataset_list of dictionaries
    dataset_list = sorted(dataset_list, key=itemgetter("AcquisitionDate",
                                                       "subject",
                                                       "session",
                                                       "ModifiedSeriesNumber",
                                                       "json_path"))

    return dataset_list


def organize_dataset(dataset_list):
    """
    Organize data files into psuedo subject (and session, if appplicable) groups.
    This is particularily necessary when anaonymized data is provided, since crucial
    metadata including AcquisitionDateTime, PatientName, PatientID, etc are removed.
    Typically, these fields assist ezBIDS in determining subject (and session) mapping,
    so will try to use other metadata (AcquisitionTime, SeriesNumber, etc) to perform
    this important mapping. This is very brittle, so users should be informed before
    uploading to either explicitly state subject and session mappings (e.g., sub-001)
    in the file name or path, or not upload anonymized data.

    Parameters
    ----------
    dataset_list: list
        List of dictionaries containing pertinent and unique information about
        the data, primarily coming from the metadata in the json files

    Returns
    -------
    dataset_list: list
        Same as input, but with information to help perform subject (and session) mapping
    """

    dataset_list = sorted(dataset_list, key=itemgetter(
        "subject",
        "AcquisitionTime",
        "ModifiedSeriesNumber")
    )

    pseudo_sub = 1
    for index, unique_dic in enumerate(dataset_list):
        if unique_dic["subject"] == "n/a":
            if (unique_dic["AcquisitionDateTime"] == "0000-00-00T00:00:00.000000"
                    and unique_dic["PatientName"] == "n/a"
                    and unique_dic["PatientID"] == "n/a"):
                # Likely working with anonymized data, so not obvious what subject/session mapping should be
                if index == 0:
                    subj = pseudo_sub
                else:
                    previous_data = dataset_list[index - 1]
                    if unique_dic["SeriesNumber"] >= previous_data["SeriesNumber"]:
                        if not unique_dic["SeriesNumber"] - previous_data["SeriesNumber"] < 2:
                            # Probably a misalignment, adjust pseudo subject ID
                            subj = pseudo_sub - 1
                        else:
                            subj = pseudo_sub
                    else:
                        if int(unique_dic["SeriesNumber"]) == 1:
                            # Likely moving onto data from new subject or session, but going to assuming subject
                            pseudo_sub += 1
                        subj = pseudo_sub

                unique_dic["subject"] = (unique_dic["subject"] + ("0" * (4 - len(str(subj)))) + str(subj))
                unique_dic["AcquisitionDateTime"] = unique_dic["subject"][:-4]

        dataset_list = sorted(dataset_list, key=itemgetter(
            "subject",
            "AcquisitionTime",
            "ModifiedSeriesNumber")
        )

    return dataset_list


def determine_subj_ses_IDs(dataset_list, bids_compliant):
    """
    Determine subject ID(s), and session ID(s) (if applicable) of uploaded
    dataset.

    Parameters
    ----------
    dataset_list: list
        List of dictionaries containing pertinent and unique information about
        the data, primarily coming from the metadata in the json files

    Returns
    -------
    dataset_list: list
        List of dictionaries containing pertinent and unique information about
        the data, primarily coming from the metadata in the json files

    subject_ids_info: list
        List of dictionaries containing subject identification info, such as
        PatientID, PatientName, PatientBirthDate, and corresponding session
        information

    """
    date_counter = 1
    subject_idx_counter = 0
    subjects_information = []
    participants_info = {}
    # Determine unique subjects from uploaded dataset
    for sub in np.unique([x["subject"] for x in dataset_list]):
        sub_dics_list = [x for x in dataset_list if x["subject"] == sub]

        # Give each subject a unique subject_idx value
        for x in sub_dics_list:
            x["subject_idx"] = subject_idx_counter
        subject_idx_counter += 1

        # Organize phenotype (e.g., sex, age) information
        bids_root_dir = pd.read_csv(f"{DATA_DIR}/bids_compliant.log", header=None).iloc[0][0]
        if bids_compliant == "yes" and os.path.isfile(f"{bids_root_dir}/participants.tsv"):
            participants_info_data = pd.read_csv(f"{bids_root_dir}/participants.tsv", sep="\t")

            participants_info = {}
            participants_info_columns = ([x for x in participants_info_data.columns if x != "participant_id"]
                                         + ["PatientName", "PatientID"])

            for len_index in range(len(participants_info_data)):
                participants_info[str(len_index)] = dict.fromkeys(participants_info_columns)

                for col in participants_info_columns:
                    if col not in ["PatientName", "PatientID"]:
                        participants_info[str(len_index)][col] = str(participants_info_data[col].iloc[len_index])
                    else:
                        if "sub-" in participants_info_data["participant_id"].iloc[len_index]:
                            participant_id = participants_info_data["participant_id"].iloc[len_index].split("-")[-1]
                        else:
                            participant_id = participants_info_data["participant_id"].iloc[len_index]

                        participants_info[str(len_index)]["PatientName"] = str(participant_id)
                        participants_info[str(len_index)]["PatientID"] = str(participant_id)
        else:
            phenotype_info = list(
                {
                    "sex": x["PatientSex"],
                    "age": x["PatientAge"],
                    "PatientName": x["PatientName"],
                    "PatientID": x["PatientID"]
                } for x in sub_dics_list)[0]

            participants_info.update({str(x["subject_idx"]): phenotype_info})

        # Determine all unique sessions (if applicable) per subject
        unique_ses_date_times = []
        session_idx_counter = 0
        ses_dates = list(set([(x["session"], x["AcquisitionDate"]) for x in sub_dics_list]))

        # Session information includes the following metadata: session, AcquisitionDate, and AcquisitionTime
        for ses_date in ses_dates:
            ses_date = list(ses_date)
            date_time = [
                x["AcquisitionTime"] for x in sub_dics_list if x["session"] == ses_date[0]
                and x["AcquisitionDate"] == ses_date[1]][0]
            ses_date.append(date_time)
            dic = {
                "session": ses_date[0],
                "AcquisitionDate": ses_date[1],
                "AcquisitionTime": ses_date[2],
                "exclude": False,
                "session_idx": 0
            }
            unique_ses_date_times.append(dic)

        # Sorting method is determined by whether or not the uploaded data is anonymized
        if unique_ses_date_times[0]["AcquisitionDate"] != "0000-00-00":
            unique_ses_date_times = sorted(unique_ses_date_times, key=itemgetter("AcquisitionDate",
                                                                                 "AcquisitionTime",
                                                                                 "session"))
        else:
            unique_ses_date_times = sorted(unique_ses_date_times, key=itemgetter("session"))

        # For each session per subject, give a unique session_idx value
        for dic in unique_ses_date_times:
            dic["session_idx"] = session_idx_counter
            session_idx_counter += 1

        # Pair patient information (PatientName, PatientID, PatientBirthDate) with corresponding session information
        patient_info = []
        for ses_info in unique_ses_date_times:
            patient_dic = {
                "PatientName": [
                    x["PatientName"] for x in sub_dics_list if x["session"] == ses_info["session"]
                    and x["AcquisitionDate"] == ses_info["AcquisitionDate"]][0],
                "PatientID": [
                    x["PatientID"] for x in sub_dics_list if x["session"] == ses_info["session"]
                    and x["AcquisitionDate"] == ses_info["AcquisitionDate"]][0],
                "PatientBirthDate": [
                    x["PatientBirthDate"] for x in sub_dics_list if x["session"] == ses_info["session"]
                    and x["AcquisitionDate"] == ses_info["AcquisitionDate"]][0]
            }
            patient_info.append(patient_dic)

        """
        See if multiple sessions occurred on same day, meaning same AcquisitionDate
        If so, modify the AcquisitionDate value(s) so that each are unique, since
        ezBIDS only cares about AcquisitionDate. Modification entails appending
        a '.<value>' to the end of the AcquisitionDate value (e.g. '2021-01-01.1').
        AcquisitionDate cannot be used with anonymized data because that metadata
        is removed.
        """
        unique_ses_dates = [[x["session"], x["AcquisitionDate"]] for x in unique_ses_date_times]
        for ses_date in unique_ses_dates:
            unique_dates_dics_list = [x for x in unique_ses_date_times if x["AcquisitionDate"] == ses_date[1]]
            if len(unique_dates_dics_list) > 1:
                for date_dic in unique_dates_dics_list:
                    date_dic["AcquisitionDate"] = ses_date[1] + "." + str(date_counter)
                    date_counter += 1

        # update dataset_list with updated AcquisitionDate and session_idx info
        for sub_ses_map_dic in unique_ses_date_times:
            for data_dic in dataset_list:
                if (data_dic["subject"] == sub
                        and data_dic["session"] == sub_ses_map_dic["session"]
                        and data_dic["AcquisitionDate"] == sub_ses_map_dic["AcquisitionDate"].split(".")[0]):
                    data_dic["AcquisitionDate"] = sub_ses_map_dic["AcquisitionDate"]
                    data_dic["session_idx"] = sub_ses_map_dic["session_idx"]

        """
        Using all the information gathered above, build the subject/session
        information in format that ezBIDS can understand.
        """
        subject_ids_info = {
            "subject": sub,
            "PatientInfo": patient_info,
            "phenotype": list({"sex": x["PatientSex"], "age": x["PatientAge"]} for x in sub_dics_list)[0],
            "exclude": False,
            "sessions": [
                {k: v for k, v in d.items()
                    if k != "session_idx"
                    and k != "AcquisitionTime"} for d in unique_ses_date_times],
            "validationErrors": []
        }

        subjects_information.append(subject_ids_info)

    return dataset_list, subjects_information, participants_info


def determine_unique_series(dataset_list, bids_compliant):
    """
    From the dataset_list, lump the individual acquisitions into unique series.
    Unique data is determined from 4 dicom header values: SeriesDescription
    EchoTime, ImageType, and RepetitionTime. If EchoTime values differ
    slightly (+/- 1 ms) and other values are the same, a unique series ID is not
    given, since EchoTime is a continuous variable.

    Parameters
    ----------
    dataset_list: list
        List of dictionaries containing pertinent and unique information about
        the data, primarily coming from the metadata in the json files.

    Returns
    -------
    dataset_list_unique_series: list
        A modified version of dataset_list, where the list contains only the
        dictionaries of acquisitions with a unique series ID.
    """
    dataset_list_unique_series = []
    series_checker = []
    series_idx = 0

    for index, acquisition_dic in enumerate(dataset_list):
        """
        Assign series index value (series_idx) to each unique sequence based on
        EchoTime, SeriesDescription/ProtocolName, ImageType, and RepetitionTime metadata.
        Since EchoTime and RepetitionTime are float values, add slight measurement error
        tolerance for these metadata. See https://github.com/rordenlab/dcm2niix/issues/543

        If retro-reconstruction (RR) acquistions are found
        ("_RR" in SeriesDescription), they should be of same unique
        series as non retro-reconstruction ones. These are generally rare
        cases, but should be accounted for.
        """
        descriptor = acquisition_dic["descriptor"]
        if "_RR" in acquisition_dic["SeriesDescription"]:
            heuristic_items = [
                round(acquisition_dic["EchoTime"], 1),
                acquisition_dic[descriptor].replace("_RR", ""),
                acquisition_dic["ImageType"],
                round(acquisition_dic["RepetitionTime"], 1)
            ]
        else:
            heuristic_items = [
                round(acquisition_dic["EchoTime"], 1),
                acquisition_dic[descriptor],
                acquisition_dic["ImageType"],
                round(acquisition_dic["RepetitionTime"], 1)
            ]

        if bids_compliant == "yes":  # Each uploaded BIDS NIfTI/JSON pair is a unique series
            if index == 0:
                series_idx = 0
            else:
                series_idx += 1
            acquisition_dic["series_idx"] = series_idx
            dataset_list_unique_series.append(acquisition_dic)
        else:
            if index == 0:
                acquisition_dic["series_idx"] = 0
                dataset_list_unique_series.append(acquisition_dic)
            else:
                if heuristic_items[1:3] not in [x[1:3] for x in series_checker]:
                    series_idx += 1
                    acquisition_dic["series_idx"] = series_idx
                    dataset_list_unique_series.append(acquisition_dic)
                else:
                    if heuristic_items not in [x[:-1] for x in series_checker]:
                        series_idx += 1
                        acquisition_dic["series_idx"] = series_idx
                        dataset_list_unique_series.append(acquisition_dic)
                    else:
                        common_series_index = [x[:-1] for x in series_checker].index(heuristic_items)
                        common_series_idx = series_checker[common_series_index][-1]
                        acquisition_dic["series_idx"] = common_series_idx

            series_checker.append(heuristic_items + [acquisition_dic["series_idx"]])

    return dataset_list, dataset_list_unique_series


def create_lookup_info():
    lookup_dic = {}

    # Add localizers to lookup_dic
    lookup_dic["localizer"] = {
        "exclude": {
            "search_terms": ["localizer", "scout"],
            "accepted_entities": [],
            "required_entities": [],
            "conditions": ['"_i0000" in unique_dic["paths"][0]']
        }
    }

    for datatype in datatypes_yaml.keys():
        if datatype in accepted_datatypes:
            lookup_dic[datatype] = {}
            rule = yaml.load(open(os.path.join(analyzer_dir, datatype_suffix_rules, datatype) + ".yaml"),
                             Loader=yaml.FullLoader)

            for key in rule.keys():
                suffixes = rule[key]["suffixes"]
                if datatype == "anat":
                    # Remove deprecated suffixes
                    suffixes = [x for x in suffixes if x not in ["T2star", "FLASH", "PD"]]
                elif datatype == "dwi":
                    # suffixes = ["dwi", "sbref"]
                    suffixes = [x for x in suffixes if x in ["dwi", "sbref"]]
                elif datatype == "fmap":
                    # Remove m0scan suffix since it could go in either the perf or fmap directory
                    suffixes = [x for x in suffixes if x not in ["m0scan"]]
                elif datatype == "func":
                    # Remove non-imaging suffixes
                    suffixes = [x for x in suffixes if x not in ["events", "stim", "physio", "phase"]]
                elif datatype == "perf":
                    # Remove non-imaging suffixes
                    suffixes = [x for x in suffixes if x not in ["aslcontext", "asllabeling", "physio", "stim"]]
                elif datatype == "pet":
                    # Only keep imaging suffixes
                    suffixes = [x for x in suffixes if x == "pet"]

                for suffix in suffixes:

                    lookup_dic[datatype][suffix] = {
                        "search_terms": [suffix.lower()],
                        "accepted_entities": [],
                        "required_entities": [],
                        "conditions": []
                    }

                    if suffix in rule[key]["suffixes"]:

                        entities = rule[key]["entities"]

                        accepted_entities = [
                            x for x in entities.keys()
                            if x not in ["subject", "session"]
                        ]
                        lookup_dic[datatype][suffix]["accepted_entities"] = accepted_entities

                        required_entities = [
                            x for x in entities.keys()
                            if x not in ["subject", "session"]
                            and entities[x] == "required"
                        ]
                        lookup_dic[datatype][suffix]["required_entities"] = required_entities

                        if datatype == "anat":
                            lookup_dic[datatype][suffix]["conditions"].extend(
                                [
                                    'unique_dic["nibabel_image"].ndim == 3',

                                ]
                            )
                            if suffix == "T1w":
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "tfl3d",
                                        "tfl_3d",
                                        "mprage",
                                        "mp_rage",
                                        "spgr",
                                        "tflmgh",
                                        "tfl_mgh",
                                        "t1mpr",
                                        "t1_mpr",
                                        "anatt1",
                                        "anat_t1",
                                        "3dt1",
                                        "3d_t1"
                                    ]
                                )
                                lookup_dic[datatype][suffix]["conditions"].extend(
                                    [
                                        '"inv1" not in sd and "inv2" not in sd and "uni_images" not in sd'
                                    ]
                                )
                            elif suffix == "T2w":
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "anatt2",
                                        "anat_t2",
                                        "3dt2",
                                        "3d_t2",
                                        "t2spc",
                                        "t2_spc"
                                    ]
                                )
                                lookup_dic[datatype][suffix]["conditions"].extend(
                                    [
                                        'unique_dic["EchoTime"] > 100'
                                    ]
                                )
                            elif suffix == "FLAIR":
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "t2spacedafl",
                                        "t2_space_da_fl",
                                        "t2space_da_fl",
                                        "t2space_dafl",
                                        "t2_space_dafl"
                                    ]
                                )
                            elif suffix == "T2starw":
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "qsm"
                                    ]
                                )
                                lookup_dic[datatype][suffix]["conditions"].extend(
                                    [
                                        '"EchoNumber" not in unique_dic["sidecar"]'
                                    ]
                                )
                            elif suffix == "MEGRE":
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "qsm"
                                    ]
                                )
                                lookup_dic[datatype][suffix]["conditions"].extend(
                                    [
                                        '"EchoNumber" in unique_dic["sidecar"]'
                                    ]
                                )
                            elif suffix == "MESE":
                                lookup_dic[datatype][suffix]["conditions"].extend(
                                    [
                                        '"EchoNumber" in unique_dic["sidecar"]'
                                    ]
                                )
                            elif suffix in ["MP2RAGE", "IRT1"]:
                                lookup_dic[datatype][suffix]["conditions"].extend(
                                    [
                                        '"InversionTime" in unique_dic["sidecar"]'
                                    ]
                                )
                            elif suffix == "UNIT1":
                                lookup_dic[datatype][suffix]["search_terms"] = [
                                    "uni"
                                ]  # Often show up as "UNI" in sd
                                lookup_dic[datatype][suffix]["conditions"].extend(
                                    [
                                        '"UNI" in unique_dic["ImageType"]',
                                        '"InversionTime" not in unique_dic["sidecar"]'
                                    ]
                                )
                            elif suffix in ["MPM", "MTS"]:
                                lookup_dic[datatype][suffix]["conditions"].extend(
                                    [
                                        '"FlipAngle" in unique_dic["sidecar"]'
                                    ]
                                )
                            elif suffix == "PDT2":
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "fse",
                                        "pd_t2"
                                    ]
                                )
                        elif datatype == "func":
                            if suffix in ["bold", "sbref"]:
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "func",
                                        "bold",
                                        "fmri",
                                        "fcmri",
                                        "fcfmri",
                                        "rsfmri",
                                        "rsmri",
                                        "task",
                                        "rest"
                                    ]
                                )
                                if suffix == "bold":
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            'unique_dic["nibabel_image"].ndim == 4',
                                            'unique_dic["NumVolumes"] > 1',
                                            'unique_dic["RepetitionTime"] > 0',
                                            'not any(x in unique_dic["ImageType"] '
                                            'for x in ["DERIVED", "PERFUSION", "DIFFUSION", "ASL", "UNI"])'
                                        ]
                                    )
                                elif suffix == "sbref":
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            '"DIFFUSION" not in unique_dic["ImageType"]',
                                            '"sbref" in sd and unique_dic["NumVolumes"] == 1',
                                            'unique_dic["nibabel_image"].ndim == 3',
                                            'not any(x in unique_dic["ImageType"] '
                                            'for x in ["DERIVED", "PERFUSION", "DIFFUSION", "ASL", "UNI"])'
                                        ]
                                    )
                        elif datatype == "dwi":
                            if suffix in ["dwi", "sbref"]:
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "dwi",
                                        "dti",
                                        "dmri"
                                    ]
                                )
                                if suffix == "dwi":
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            'any(".bvec" in x for x in unique_dic["paths"])',
                                            # '"DIFFUSION" in unique_dic["ImageType"]',
                                            'unique_dic["NumVolumes"] > 1',
                                            'not any(x in sd for x in ["trace", "_fa_", "adc"])'
                                        ]
                                    )
                                elif suffix == "sbref":
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            'any(".bvec" in x for x in unique_dic["paths"])',
                                            # '"DIFFUSION" in unique_dic["ImageType"]',
                                            'not any(x in sd for x in ["trace", "_fa_", "adc"])',
                                            'unique_dic["nibabel_image"].ndim == 3',
                                            '("b0" in sd or "bzero" in sd or "sbref" in sd) '
                                            'and unique_dic["NumVolumes"] == 1'
                                        ]
                                    )
                        elif datatype == "fmap":
                            if suffix in ["epi", "magnitude1", "magnitude2", "phasediff",
                                          "phase1", "phase2", "magnitude", "fieldmap"]:
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "fmap",
                                        "fieldmap",
                                        "field_map",
                                        "grefieldmap",
                                        "gre_field_map",
                                        "distortionmap",
                                        "distortion_map"
                                    ]
                                )
                                if suffix == "epi":
                                    lookup_dic[datatype][suffix]["search_terms"].extend(
                                        [
                                            "fmap_spin",
                                            "fmap_se",
                                            "fmap_ap",
                                            "fmap_pa",
                                            "fieldmap_spin",
                                            "fieldmap_ap",
                                            "fieldmap_pa",
                                            "fieldmap_se",
                                            "spinecho",
                                            "spin_echo",
                                            "sefmri",
                                            "semri",
                                            "pepolar"
                                        ]
                                    )
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            'unique_dic["NumVolumes"] <= 10',
                                            '"EchoNumber" not in unique_dic["sidecar"]',
                                            '"Manufacturer" in unique_dic["sidecar"]',
                                            'unique_dic["sidecar"]["Manufacturer"] != "GE"'
                                        ]
                                    )
                                elif suffix == "magnitude1":
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            '"EchoNumber" in unique_dic["sidecar"]',
                                            'unique_dic["EchoNumber"] == 1',
                                            '"_e1_ph" not in unique_dic["json_path"]'
                                        ]
                                    )
                                elif suffix == "magnitude2":
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            '"EchoNumber" in unique_dic["sidecar"]',
                                            'unique_dic["EchoNumber"] == 2',
                                            '"_e2_ph" not in unique_dic["json_path"]'
                                        ]
                                    )
                                elif suffix == "phasediff":
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            '"EchoNumber" in unique_dic["sidecar"]',
                                            'unique_dic["EchoNumber"] == 2',
                                            '"_e2_ph" in unique_dic["json_path"]',
                                            '"_e1_ph" not in dataset_list_unique_series[index - 2]["json_path"]'
                                        ]
                                    )
                                elif suffix == "phase1":
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            '"EchoNumber" in unique_dic["sidecar"]',
                                            'unique_dic["EchoNumber"] == 1',
                                            '"_e1_ph" in unique_dic["json_path"]'
                                        ]
                                    )
                                elif suffix == "phase2":
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            '"EchoNumber" in unique_dic["sidecar"]',
                                            'unique_dic["EchoNumber"] == 2',
                                            '"_e2_ph" in unique_dic["json_path"]',
                                            '"_e1_ph" in dataset_list_unique_series[index - 2]["json_path"]'
                                        ]
                                    )
                                elif suffix in ["magnitude", "fieldmap"]:  # specific to GE scanners
                                    lookup_dic[datatype][suffix]["conditions"].extend(
                                        [
                                            '"Manufacturer" in unique_dic["sidecar"]',
                                            'unique_dic["sidecar"]["Manufacturer"] == "GE"'
                                        ]
                                    )
                            elif suffix == "TB1TFL":
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "tflb1map",
                                        "tfl_b1map",
                                        "tfl_b1_map"
                                    ]
                                )
                            elif suffix == "TB1RFM":
                                lookup_dic[datatype][suffix]["search_terms"].extend(
                                    [
                                        "rfmap"
                                    ]
                                )
                        elif datatype == "pet":
                            if suffix == "pet":
                                # lookup_dic[datatype][suffix]["search_terms"].extend(
                                #     [
                                #         "radiopharmaceutical",
                                #         "injectionstart"
                                #     ]
                                # )
                                lookup_dic[datatype][suffix]["conditions"].extend(
                                    [
                                        '"pypet2bids" in unique_dic["sidecar"]["ConversionSoftware"] '
                                        'or unique_dic["Modality"] == "PT"'
                                    ]
                                )

    # Add  DWI derivatives to lookup dictionary
    lookup_dic["dwi_derivatives"] = {
        "exclude": {
            "search_terms": ["trace", "_fa_", "adc"],
            "accepted_entities": [],
            "required_entities": [],
            "conditions": [
                '"DIFFUSION" in unique_dic["ImageType"]'
            ]
        }
    }

    return lookup_dic


def datatype_suffix_identification(dataset_list_unique_series, lookup_dic):
    """
    Uses metadata to try to determine the identity (i.e. datatype and suffix)
    of each unique acquisition in uploaded dataset.

    Parameters
    ----------
    dataset_list_unique_series : list
        List of dictionaries for each unique acquisition series in dataset.

    lookup_dic: dict
        Dictionary of information pertaining to datatypes and suffixes in the BIDS specification.
        Included is a series of rules/heuristics to help map imaging sequences to their appropriate
        datatype and suffix labels.

    Returns
    -------
    dataset_list_unique_series : list
        updated input list of dictionaries
    """

    """
    Schema datatype and suffix labels are helpful, but typically
    researchers label their imaging protocols in less standardized ways.
    ezBIDS will attempt to determine datatype and suffix labels based on
    common keys/labels.
    """
    for index, unique_dic in enumerate(dataset_list_unique_series):
        # Not great to use json_path because it's only the first sequence in the series_idx group
        json_path = unique_dic["json_path"]

        if not unique_dic["valid_image"]:
            """
            Likely an acquisition that doesn't actually contain imaging data, so don't convert.
            Example: "facMapReg" sequences in NYU_Shanghai dataset
            """
            unique_dic["type"] = "exclude"
            unique_dic["error"] = "Acquisition does not appear to be an acquisition with imaging data"
            unique_dic["message"] = "Acquisition is not believed to have " \
                "imaging information and therefore will not be converted " \
                "to BIDS. Please modify if incorrect."
        elif unique_dic["type"] == "exclude":
            unique_dic["error"] = "Uploaded NIfTI/JSON file wasn't converted from DICOM using " \
                "dcm2niix or pypet2bids, which is required by ezBIDS. Will not convert file, " \
                "since necessary metadata information will likely not be present."
            unique_dic["message"] = unique_dic["error"]
        else:
            # Try checking the json paths themselves for explicit information regarding datatype and suffix
            for datatype in datatypes_yaml:
                if f"/{datatype}/" in json_path:
                    unique_dic["datatype"] = datatype

                rule = yaml.load(open(os.path.join(analyzer_dir, datatype_suffix_rules, datatype) + ".yaml"),
                                 Loader=yaml.FullLoader)

                suffixes = [x for y in [rule[x]["suffixes"] for x in rule] for x in y]

                short_suffixes = [x for x in suffixes if len(x) < 3]

                unhelpful_suffixes = [
                    "fieldmap",
                    "beh",
                    "epi",
                    "magnitude",
                    "magnitude1",
                    "magnitude2",
                    "phasediff"
                ]

                bad_suffixes = short_suffixes + unhelpful_suffixes

                # Remove deprecated suffixes
                deprecated_suffixes = ["T2star", "FLASH", "PD", "phase"]
                suffixes = [x for x in suffixes if x not in deprecated_suffixes]

                for suffix in suffixes:
                    if f"_{suffix}.json" in json_path:
                        unique_dic["suffix"] = suffix

                for bad_suffix in bad_suffixes:
                    if f"_{bad_suffix}.json" in json_path:
                        if bad_suffix == "fieldmap":
                            unique_dic["datatype"] = "fmap"
                        elif bad_suffix == "beh":
                            unique_dic["datatype"] = "beh"
                        elif bad_suffix == "epi":
                            unique_dic["datatype"] = "fmap"
                        elif bad_suffix == "magnitude":
                            unique_dic["datatype"] = "fmap"
                        elif bad_suffix == "magnitude1":
                            unique_dic["datatype"] = "fmap"
                        elif bad_suffix == "magnitude2":
                            unique_dic["datatype"] = "fmap"
                        elif bad_suffix == "phasediff":
                            unique_dic["datatype"] = "fmap"
                        elif bad_suffix == "PC":
                            unique_dic["datatype"] = "micr"
                        elif bad_suffix == "DF":
                            unique_dic["datatype"] = "micr"

                        unique_dic["suffix"] = bad_suffix

                # Correct BIDS deprecation issue, func/phase no long exists, now func/bold part-phase
                if unique_dic["datatype"] == "func" and unique_dic["suffix"] == "phase":
                    unique_dic["suffix"] = "bold"

                if unique_dic["datatype"] != "" and unique_dic["suffix"] != "":
                    unique_dic["message"] = "Acquisition is believed to be " \
                        f"{unique_dic['datatype']}/{unique_dic['suffix']} " \
                        f"because '{unique_dic['suffix']}' is in the file path. " \
                        f"Please modify if incorrect."

        # If no luck with the json paths, try with search terms in SeriesDescription (or ProtocolName) and rules
        descriptor = unique_dic["descriptor"]
        sd = unique_dic[descriptor]

        # Make easier to find search terms in the SeriesDescription (or ProtocolName)
        sd = re.sub("[^A-Za-z0-9]+", "_", sd).lower() + "_"
        # sd_sparse = re.sub("[^A-Za-z0-9]+", "", sd)

        if (not unique_dic["datatype"] or not unique_dic["suffix"]) and unique_dic["type"] == "":
            # Actual BIDS specification data
            cont = True
            for datatype in lookup_dic.keys():
                if datatype not in ["localizer", "dwi_derivatives"]:
                    suffixes = lookup_dic[datatype].keys()
                    for suffix in suffixes:
                        search_terms = lookup_dic[datatype][suffix]["search_terms"]
                        conditions = lookup_dic[datatype][suffix]["conditions"]
                        eval_checks = [eval(t, {"sd": sd,
                                                "unique_dic": unique_dic,
                                                "dataset_list_unique_series": dataset_list_unique_series,
                                                "index": index
                                                }) for t in conditions]
                        if any(x in sd for x in search_terms):
                            # Search term match
                            conditions = [
                                (x.replace("unique_dic", "").replace('["', "").replace('"]', "").
                                    replace("dataset_list_unique_series[index - 2]", "")) for x in conditions
                            ]
                            search_hit = [x for x in search_terms if re.findall(x, sd)][0]

                            if len([t for t in eval_checks if t is True]) == len(conditions):
                                # Search term match, and all conditions met for datatype/suffix pair
                                unique_dic["datatype"] = datatype
                                unique_dic["suffix"] = suffix
                                unique_dic["type"] = ""
                                if len(conditions):
                                    condition_passes = [
                                        f"({index+1}): {value}" for index, value in enumerate(conditions)
                                    ]
                                    unique_dic["message"] = f"Acquisition is believed to be {datatype}/{suffix} " \
                                        f"because '{search_hit}' is in the {unique_dic['descriptor']} and the " \
                                        f"following conditions are met: {condition_passes}. " \
                                        "Please modify if incorrect."
                                else:
                                    unique_dic["message"] = f"Acquisition is believed to be {datatype}/{suffix} " \
                                        f"because '{search_hit}' is in the {unique_dic['descriptor']}. " \
                                        "Please modify if incorrect."
                                cont = False
                                break
                            else:
                                unique_dic["type"] = "exclude"
                                condition_fails_ind = [i for (i, v) in enumerate(eval_checks) if v is False]
                                condition_fails = [v for (i, v) in enumerate(conditions) if i in condition_fails_ind]
                                condition_fails = [
                                    f"({index+1}): {value}" for index, value in enumerate(condition_fails)
                                ]

                                if (datatype in ["func", "dwi"]
                                        and (unique_dic["nibabel_image"].ndim == 3 and unique_dic["NumVolumes"] > 1)):
                                    """
                                    func and dwi can also have sbref suffix pairings, so 3D dimension data with
                                    only a single volume likely indicates that the sequence was closer to being
                                    identified as a func (or dwi) sbref.
                                    """
                                    suffix = "sbref"

                                unique_dic["message"] = f"Acquisition was thought to be {datatype}/{suffix} " \
                                    f"because '{search_hit}' is in the {unique_dic['descriptor']}, but the " \
                                    f"following conditions were not met: {condition_fails}. Please modify " \
                                    "if incorrect."

                        elif datatype == "dwi" and suffix == "dwi" and any(".bvec" in x for x in unique_dic["paths"]):
                            unique_dic["datatype"] = datatype
                            unique_dic["suffix"] = suffix
                            unique_dic["message"] = f"Acquisition is believed to be {datatype}/{suffix} " \
                                "because associated bval/bvec files were found for this sequence. " \
                                "Please modify if incorrect."
                    if cont is False:
                        break
                else:
                    # Localizers
                    if datatype == "localizer":
                        search_terms = lookup_dic[datatype]["exclude"]["search_terms"]
                        conditions = lookup_dic["localizer"]["exclude"]["conditions"]
                        eval_checks = [eval(t, {"sd": sd, "unique_dic": unique_dic}) for t in conditions]
                        if (any(x in sd for x in search_terms)
                                or len([t for t in eval_checks if t]) == len(conditions)):
                            unique_dic["type"] = "exclude"
                            unique_dic["error"] = "Acquisition appears to be a localizer"
                            unique_dic["message"] = "Acquisition is believed to be a " \
                                "localizer and will therefore not be converted to BIDS. Please " \
                                "modify if incorrect."
                    # DWI derivatives (TRACEW, FA, ADC)
                    elif datatype == "dwi_derivatives":
                        search_terms = lookup_dic[datatype]["exclude"]["search_terms"]
                        conditions = lookup_dic["dwi_derivatives"]["exclude"]["conditions"]
                        eval_checks = [eval(t, {"sd": sd, "unique_dic": unique_dic}) for t in conditions]
                        if (any(x in sd for x in search_terms)
                                and len([t for t in eval_checks if t]) == len(conditions)):
                            unique_dic["type"] = "exclude"
                            unique_dic["error"] = "Acquisition appears to be a TRACEW, FA, or " \
                                "ADC, which are unsupported by ezBIDS and will therefore not " \
                                "be converted."
                            unique_dic["message"] = "Acquisition is believed to be a dwi derivative " \
                                "(TRACEW, FA, ADC), which are not supported by BIDS and will not " \
                                "be converted. Please modify if incorrect."

            """
            Can't determine datatype and suffix pairing, assume not BIDS-compliant acquisition,
            unless user specifies otherwise;
            """
            if ((unique_dic["datatype"] == "" or unique_dic["suffix"] == "")
                    and unique_dic["type"] == "" and unique_dic["message"] is None):
                unique_dic["error"] = "Acquisition cannot be resolved. Please " \
                    "determine whether or not this acquisition should be " \
                    "converted to BIDS."
                unique_dic["message"] = "Acquisition is unknown because there " \
                    "is not enough adequate information. Please modify if " \
                    "acquisition is desired for BIDS conversion, otherwise " \
                    "the acquisition will not be converted."
                unique_dic["type"] = "exclude"

        # Combine datatype and suffix to create type variable, which is needed for internal brainlife.io storage
        if "exclude" not in unique_dic["type"]:
            unique_dic["type"] = unique_dic["datatype"] + "/" + unique_dic["suffix"]

        """
        For non-normalized anatomical acquisitions, provide message that
        they may have poor CNR and should consider excluding them from BIDS
        conversion if a corresponding normalized acquisition is present.
        """
        if unique_dic["datatype"] == "anat" and "NORM" not in unique_dic["ImageType"]:
            unique_dic["message"] = unique_dic["message"] + (" Additionally, this acquisition appears to be "
                                                             "non-normalized, potentially having poor CNR. "
                                                             "If there is a corresponding normalized acquisition "
                                                             "('NORM' in the ImageType metadata field), consider "
                                                             "excluding this current one from BIDS conversion."
                                                             )

        # Warn user about non-RMS multi-echo anatomical acquisitions
        if (unique_dic["datatype"] == "anat" and "EchoNumber" in unique_dic["sidecar"]
                and "MEAN" not in unique_dic["ImageType"]):
            # unique_dic["type"] = "exclude"
            unique_dic["message"] = unique_dic["message"] + (
                " Acquisition also appears to be an anatomical multi-echo, but not the "
                "combined RMS file. If the RMS file exists it is ideal to exclude this "
                "acquisition and only save the RMS file, not the individual echoes.")

    """
    If there's multi-echo anatomical data and we have the mean (RMS) file, exclude
    the the individual echo sequences, since the validator fails on them.
    """
    anat_ME_RMS = [
        ind for (ind, v) in enumerate(dataset_list_unique_series)
        if v["datatype"] == "anat"
        and "MEAN" in v["ImageType"]
    ]

    if len(anat_ME_RMS):
        for anat_ME_RMS_index in anat_ME_RMS:
            sd = dataset_list_unique_series[anat_ME_RMS_index][descriptor]
            anat_ind_ME_indices = [
                x for (x, v) in enumerate(dataset_list_unique_series)
                if re.sub("[^A-Za-z0-9]+", "", v[descriptor]) == re.sub("[^A-Za-z0-9]+", "", sd).replace("RMS", "")
            ]

            for anat_ind_ME_index in anat_ind_ME_indices:
                dataset_list_unique_series[anat_ind_ME_index]["message"] = (
                    " A mean RMS anatomical file combining the multiple echoes has been found, "
                    "thus this individual anatomical echo file will be excluded from conversion. "
                    "Please modify if incorrect."
                )
                dataset_list_unique_series[anat_ind_ME_index]["type"] = "exclude"

    # sys.exit()
    return dataset_list_unique_series


def entity_labels_identification(dataset_list_unique_series, lookup_dic):
    """
    Function to determine acquisition entity label information (e.g. dir-, echo-)
    based on acquisition metadata. Entities are then sorted in accordance with
    BIDS specification ordering.

    Parameters
    ----------
    dataset_list_unique_series : list
        List of dictionaries for each unique acquisition series in dataset.

    lookup_dic: dict
        Dictionary of information pertaining to datatypes and suffixes in the BIDS specification.
        Included is a series of rules/heuristics to help map imaging sequences to their appropriate
        datatype and suffix labels.

    Returns
    -------
    dataset_list_unique_series : list
        updated input list
    """
    entity_ordering = yaml.load(open(os.path.join(analyzer_dir, entity_ordering_file)), Loader=yaml.FullLoader)

    tb1afi_tr = 1
    tb1srge_td = 1
    for unique_dic in dataset_list_unique_series:

        series_entities = {}
        descriptor = unique_dic["descriptor"]
        regex = r'[^\w.]'  # "[^A-Za-z0-9]+"
        sd = re.sub(regex, "_", unique_dic[descriptor]).lower() + "_"
        json_path = unique_dic["json_path"]

        # Check to see if entity labels can be determined from BIDS naming convention
        for key in entities_yaml:
            if key not in ["subject", "session", "direction"]:  # ezBIDS already knows PED for dir entity label
                entity = entities_yaml[key]['entity']
                if f"_{entity}_" in sd:
                    # series_entities[key] = re.split(regex, sd.split(f"{entity}_")[-1])[0].replace("_", "")
                    series_entities[key] = re.split('_', sd.split(f"{entity}_")[-1])[0]
                elif f"_{entity}-" in json_path:
                    series_entities[key] = re.split('[^a-zA-Z0-9]', json_path.split(f"{entity}-")[-1])[0]
                else:
                    series_entities[key] = ""
            else:
                series_entities[key] = ""

        # If BIDS naming convention isn't detected, do a more thorough check for certain entities labels

        # task
        func_rest_keys = ["rest", "rsfmri", "fcmri"]
        if any(x in re.sub("[^A-Za-z0-9]+", "", sd).lower() for x in func_rest_keys) and not series_entities["task"]:
            series_entities["task"] = "rest"
        else:
            match_index = [
                x for x, y in enumerate(re.search(x, sd, re.IGNORECASE) for x in cog_atlas_tasks) if y is not None
            ]
            if len(match_index):
                series_entities["task"] = cog_atlas_tasks[match_index[0]]

        # dir (required for fmap/epi and highly recommended for dwi/dwi)
        if any(x in unique_dic["type"] for x in ["fmap/epi", "dwi/dwi"]):
            series_entities["direction"] = unique_dic["direction"]

        # echo
        if (unique_dic["EchoNumber"]
            and not any(x in unique_dic["type"] for x in ["fmap/epi",
                                                          "fmap/magnitude1",
                                                          "fmap/magnitude2",
                                                          "fmap/phasediff",
                                                          "fmap/phase1",
                                                          "fmap/phase2",
                                                          "fmap/fieldmap"])):
            series_entities["echo"] = str(unique_dic["EchoNumber"])

        # flip
        if (any(x in unique_dic["type"] for x in ["anat/VFA", "anat/MPM", "anat/MTS", "fmap/TB1EPI", "fmap/TB1DAM"])
                and "FlipAngle" in unique_dic["sidecar"]):
            regex = re.compile('flip([1-9]*)')
            try:
                series_entities["flip"] = regex.findall(re.sub("[^A-Za-z0-9]+", "", sd))[0]
            except:
                series_entities["flip"] = ""

        # acq
        if any(x in unique_dic["type"] for x in ["fmap/TB1TFL", "fmap/TB1RFM"]):
            if "FLIP ANGLE MAP" in unique_dic["ImageType"]:
                series_entities["acquisition"] = "fmap"
            else:
                series_entities["acquisition"] = "anat"

        if any(x in unique_dic["type"] for x in ["fmap/TB1AFI"]):
            series_entities["acquisition"] = "tr" + str(tb1afi_tr)
            tb1afi_tr += 1

        if any(x in unique_dic["type"] for x in ["fmap/TB1SRGE"]) and "DelayTime" in unique_dic["sidecar"]:
            series_entities["acquisition"] = "td" + str(tb1srge_td)
            tb1srge_td += 1

        if any(x in unique_dic["type"] for x in ["fmap/RB1COR"]) and "ReceiveCoilName" in unique_dic["sidecar"]:
            if "Head" in unique_dic["sidecar"]["ReceiveCoilName"]:
                series_entities["acquisition"] = "head"
            elif "Body" in unique_dic["sidecar"]["ReceiveCoilName"]:
                series_entities["acquisition"] = "body"

        # inversion
        if (any(x in unique_dic["type"] for x in ["anat/MP2RAGE", "anat/IRT1"])
                and "InversionTime" in unique_dic["sidecar"]):
            # inversion_time = unique_dic["sidecar"]["InversionTime"]
            regex = re.compile('inv([1-9]*)')
            try:
                series_entities["inversion"] = regex.findall(re.sub("[^A-Za-z0-9]+", "", sd))[0]
            except:
                series_entities["inversion"] = ""

        # part
        if "REAL" in unique_dic["ImageType"]:
            series_entities["part"] = "real"
        elif "IMAGINARY" in unique_dic["ImageType"]:
            series_entities["part"] = "imag"
        elif "fmap" not in unique_dic["type"] and "PHASE" in unique_dic['ImageType']:
            series_entities["part"] = "phase"
        else:
            pass

        # Make sure any found entities are allowed for specific datatype/suffix pair
        if unique_dic["type"] != "exclude":
            datatype = unique_dic["datatype"]
            suffix = unique_dic["suffix"]
            exposed_entities = [x[0] for x in series_entities.items() if x[1] != ""]

            for exposed_entity in exposed_entities:
                accepted_entities = lookup_dic[datatype][suffix]["accepted_entities"]
                if exposed_entity not in accepted_entities:
                    if datatype == "anat" and exposed_entity == "echo":
                        """
                        BIDS is probably going to allow echo entity label for anatomical,
                        even though currently the BIDS validator will fail in this instance.
                        See https://github.com/bids-standard/bids-specification/pull/1570
                        """
                        pass
                    else:
                        series_entities[exposed_entity] = ""

        """
        Replace periods in series entities with "p", if found. If other
        non alphanumeric characters are found in the entity labels, remove them
        """
        for key, value in series_entities.items():
            if "." in value:
                series_entities[key] = value.replace(".", "p")
            elif not value.isalpha():
                series_entities[key] = re.sub("[^A-Za-z0-9]+", "", value)
            else:
                pass

        # Order the entities labels according to the BIDS specification
        series_entities = dict(sorted(series_entities.items(), key=lambda pair: entity_ordering.index(pair[0])))

        unique_dic["entities"] = series_entities

    return dataset_list_unique_series


def check_part_entity(dataset_list_unique_series):
    """
    Certain data contain the part-phase entity key/value pair. If this occurs, expose the part-mag key/value pair
    for the corresponding data.
    """
    part_phase_data = [x for x in dataset_list_unique_series if x["entities"]["part"] == "phase"]

    for part in part_phase_data:
        mag_data = [
            x for x in dataset_list_unique_series if x != part
            and x["SeriesDescription"] == part["SeriesDescription"]
            and x["type"] == part["type"]
            and ({key: val for key, val in x["entities"].items() if key != "part"}
                 == {key: val for key, val in part["entities"].items() if key != "part"})
        ]

        if len(mag_data) and len(mag_data) == 1:
            mag_data[0]["entities"]["part"] = "mag"

    return dataset_list_unique_series


def update_dataset_list(dataset_list, dataset_list_unique_series):
    """
    Update the dataset_list with information that we found from the unique
    series list. Since the unique_series_list does not contain all dataset
    acquisitions, use the unique series ID (series_idx) to port information
    over.
    """
    for unique_dic in dataset_list_unique_series:
        for data in dataset_list:
            if data["series_idx"] == unique_dic["series_idx"]:
                data["entities"] = unique_dic["entities"]
                data["type"] = unique_dic["type"]
                data["forType"] = unique_dic["forType"]
                data["error"] = unique_dic["error"]
                data["message"] = unique_dic["message"]
                data["IntendedFor"] = unique_dic["IntendedFor"]
                data["B0FieldIdentifier"] = unique_dic["B0FieldIdentifier"]
                data["B0FieldSource"] = unique_dic["B0FieldSource"]

    return dataset_list


def modify_objects_info(dataset_list):
    """
    Make any necessary changes to the objects level, which primarily entails
    adding a section ID value to each acquisition, creating image screenshots,
    and clean up (i.e. removing identifying metadata information).

    Parameters
    ----------
    dataset_list : list
        List of dictionaries containing pertinent and unique information about
        the data, primarily coming from the metadata in the json files

    Returns
    -------
    objects_list : list
        List of dictionaries of all dataset acquisitions
    """
    objects_list = []

    entity_ordering = yaml.load(open(os.path.join(analyzer_dir, entity_ordering_file)), Loader=yaml.FullLoader)

    # Find unique subject/session idx pairs in dataset and sort them
    subj_ses_pairs = [[x["subject_idx"], x["session_idx"]] for x in dataset_list]
    unique_subj_ses_pairs = sorted([list(i) for i in set(tuple(i) for i in subj_ses_pairs)])

    for unique_subj_ses in unique_subj_ses_pairs:
        scan_protocol = [
            x for x in dataset_list
            if x["subject_idx"] == unique_subj_ses[0]
            and x["session_idx"] == unique_subj_ses[1]
        ]

        objects_data = []

        """
        Peruse scan protocol to check for potential issues and add some
        additional information.
        """
        for protocol in scan_protocol:
            image = protocol["nibabel_image"]
            protocol["headers"] = str(image.header).splitlines()[1:]

            object_img_array = image.dataobj
            # PET images are scaled, type will be float <f4
            if (object_img_array.dtype not in ["<i2", "<u2", "int16", "uint16"]
                    and protocol.get("sidecar", {}).get("Modality", "") != "PT"):
                # Weird edge case where data array is RGB instead of integer
                protocol["exclude"] = True
                protocol["error"] = "The data array for this " \
                    "acquisition is improper, suggesting that " \
                    "this isn't an imaging file or is a non-BIDS " \
                    "specified acquisition and will not be converted. " \
                    "Please modify if incorrect."
                protocol["message"] = protocol["error"]
                protocol["type"] = "exclude"

            # Check for negative dimesions and exclude from BIDS conversion if they exist
            if len([x for x in image.shape if x < 0]):
                protocol["exclude"] = True
                protocol["type"] = "exclude"
                protocol["error"] = "Image contains negative dimension(s) and cannot be converted to BIDS format"
                protocol["message"] = "Image contains negative dimension(s) and cannot be converted to BIDS format"

            if protocol["error"]:
                protocol["error"] = [protocol["error"]]
            else:
                protocol["error"] = []

            objects_entities = dict(zip([x for x in entities_yaml], [""] * len([x for x in entities_yaml])))

            # Re-order entities to what BIDS expects
            objects_entities = dict(sorted(objects_entities.items(), key=lambda pair: entity_ordering.index(pair[0])))

            # Make items list (part of objects list)
            items = []
            for item in protocol["paths"]:
                if ".bval" in item:
                    items.append({"path": item,
                                  "name": "bval"})
                elif ".bvec" in item:
                    items.append({"path": item,
                                  "name": "bvec"})
                elif ".json" in item:
                    items.append({"path": item,
                                  "name": "json",
                                  "sidecar": protocol["sidecar"]})
                elif ".nii.gz" in item:
                    items.append({"path": item,
                                  "name": "nii.gz",
                                  "pngPaths": [],
                                  "moviePath": None,
                                  "headers": protocol["headers"]})

            # Objects-level info for ezBIDS_core.json
            objects_info = {"subject_idx": protocol["subject_idx"],
                            "session_idx": protocol["session_idx"],
                            "series_idx": protocol["series_idx"],
                            "AcquisitionDate": protocol["AcquisitionDate"],
                            "AcquisitionTime": protocol["AcquisitionTime"],
                            "SeriesNumber": protocol["SeriesNumber"],
                            "ModifiedSeriesNumber": protocol["ModifiedSeriesNumber"],
                            "IntendedFor": protocol["IntendedFor"],
                            "B0FieldIdentifier": protocol["B0FieldIdentifier"],
                            "B0FieldSource": protocol["B0FieldSource"],
                            "entities": objects_entities,
                            "items": items,
                            "PED": protocol["direction"],
                            "analysisResults": {
                                "NumVolumes": protocol["NumVolumes"],
                                "errors": protocol["error"],
                                "warnings": [],
                                "filesize": protocol["filesize"],
                                "orientation": protocol["orientation"],
                                "section_id": 1}
                            }
            objects_data.append(objects_info)

        objects_list.append(objects_data)

    # Flatten list of lists
    objects_list = [x for y in objects_list for x in y]

    return objects_list


def extract_series_info(dataset_list_unique_series):
    """
    Extract a subset of the acquistion information, which will be displayed on
    the Series-level page of the ezBIDS UI.

    Parameters
    ----------
    dataset_list_unique_series : list
        List of dictionaries for each unique acquisition series in dataset.

    Returns
    -------
    ui_series_info_list : list
        List of dictionaries containing subset of acquisition information to be
        displayed to user on ezBIDS Series-level UI
    """
    ui_series_info_list = []
    for unique_dic in dataset_list_unique_series:
        ui_series_info = {
            "SeriesDescription": unique_dic["SeriesDescription"],
            "EchoTime": unique_dic["EchoTime"],
            "ImageType": unique_dic["ImageType"],
            "RepetitionTime": unique_dic["RepetitionTime"],
            "NumVolumes": unique_dic["NumVolumes"],
            "IntendedFor": unique_dic["IntendedFor"],
            "B0FieldIdentifier": unique_dic["B0FieldIdentifier"],
            "B0FieldSource": unique_dic["B0FieldSource"],
            "nifti_path": unique_dic["nifti_path"],
            "series_idx": unique_dic["series_idx"],
            "AcquisitionDateTime": unique_dic["AcquisitionDateTime"],
            "entities": unique_dic["entities"],
            "type": unique_dic["type"],
            "forType": unique_dic["forType"],
            "error": unique_dic["error"],
            "message": unique_dic["message"],
            "object_indices": []
        }

        ui_series_info_list.append(ui_series_info)

    return ui_series_info_list


def setVolumeThreshold(dataset_list_unique_series, objects_list):
    """
    Determine a volume threshold for all func/bold acquisitions in dataset,
    using the following heuristic:

    Parameters
    ----------
    dataset_list_unique_series : list
        List of dictionaries of unique series
    objects_list: list
        List of dictionaries of all dataset objects
    """

    func_series = [
        x for x in dataset_list_unique_series
        if "func" in x["type"]
        and x["type"] != "func/sbref"
        and x["RepetitionTime"] > 0
    ]

    if len(func_series):
        for func in func_series:
            series_idx = func["series_idx"]
            tr = func["RepetitionTime"]
            corresponding_objects_volumes = [
                x["analysisResults"]["NumVolumes"] for x in objects_list if x["series_idx"] == series_idx
            ]
            minNumVolumes = min(corresponding_objects_volumes)
            maxNumVolumes = max(corresponding_objects_volumes)
            numVolumes1min = floor(60 / tr)

            if maxNumVolumes <= numVolumes1min:  # set default as # volumes after 1 minute
                volumeThreshold = numVolumes1min
            else:
                if minNumVolumes == maxNumVolumes:  # set threshold at max NumVolumes
                    volumeThreshold = maxNumVolumes
                else:  # set threshold at 50% of max NumVolumes, or min NumVolumes if it's greater than half
                    half = floor(maxNumVolumes / 2)
                    if minNumVolumes > half:
                        volumeThreshold = minNumVolumes
                    else:
                        volumeThreshold = half

            volumeThreshold = 9  # temporary, but setting threshold low for debugging purposes

            # With volume threshold, exclude objects that don't pass it
            corresponding_objects = [x for x in objects_list if x["series_idx"] == series_idx]
            for obj in corresponding_objects:
                if obj["analysisResults"]["NumVolumes"] < volumeThreshold:
                    obj["exclude"] = True
                    obj["analysisResults"]["errors"] = ["Acquisition is believed to be func/bold and contains "
                                                        f"{obj['analysisResults']['NumVolumes']} volumes, which "
                                                        f"is less than the threshold value of {volumeThreshold} "
                                                        "this acquisition will be excluded from BIDS conversion. "
                                                        "Please modify if incorrect"]

# Begin (Apply functions)


print("########################################")
print("Beginning conversion process of uploaded dataset")
print("########################################")
print("")

# README
readme = generate_readme(DATA_DIR, bids_compliant)

# dataset description information
dataset_description_dic = generate_dataset_description(DATA_DIR, bids_compliant)

# participantsColumn portion of ezBIDS_core.json
participants_column_info = generate_participants_columns(DATA_DIR, bids_compliant)

# Generate list of all possible Cognitive Atlas task terms
cog_atlas_tasks = find_cog_atlas_tasks(cog_atlas_url)

# Load dataframe containing all uploaded files
uploaded_json_list = pd.read_csv("list", header=None, lineterminator='\n').to_numpy().flatten().tolist()

# finalized_configuration(uploaded_json_list)

# Filter for files that ezBIDS can't use
uploaded_files_list, data_type = modify_uploaded_dataset_list(uploaded_json_list)

# Create the dataset list of dictionaries
dataset_list = generate_dataset_list(uploaded_files_list, data_type)

# Get pesudo subject (and session) info
dataset_list = organize_dataset(dataset_list)

# Determine subject (and session) information
dataset_list, subjects_information, participants_info = determine_subj_ses_IDs(dataset_list, bids_compliant)

# Make a new list containing the dictionaries of only unique dataset acquisitions
dataset_list, dataset_list_unique_series = determine_unique_series(dataset_list, bids_compliant)

# Generate lookup information directory to help with datatype and suffix identification (and to some degree, entities)
lookup_dic = create_lookup_info()

# Identify datatype and suffix information
dataset_list_unique_series = datatype_suffix_identification(dataset_list_unique_series, lookup_dic)

# Identify entity label information
dataset_list_unique_series = entity_labels_identification(dataset_list_unique_series, lookup_dic)
print("--------------------------")
print("ezBIDS sequence message")
print("--------------------------")
for index, unique_dic in enumerate(dataset_list_unique_series):
    print(unique_dic["message"])
    print("")

dataset_list_unique_series = check_part_entity(dataset_list_unique_series)

# If BIDS-compliant dataset uploaded, set and apply IntendedFor mapping
dataset_list_unique_series = set_IntendedFor_B0FieldIdentifier_B0FieldSource(dataset_list_unique_series, bids_compliant)

# Port series level information to all other acquistions (i.e. objects level) with same series info
dataset_list = update_dataset_list(dataset_list, dataset_list_unique_series)

# Apply a few other changes to the objects level
objects_list = modify_objects_info(dataset_list)

# Map unique series IDs to all other acquisitions in dataset that have those parameters
print("------------------")
print("ezBIDS overview")
print("------------------")
for index, unique_dic in enumerate(dataset_list_unique_series):
    print(
        f"Unique data acquisition file {unique_dic['nifti_path']}, "
        f"Series Description {unique_dic['SeriesDescription']}, "
        f"was determined to be {unique_dic['type']}, "
        f"with entity labels {[x for x in unique_dic['entities'].items() if x[-1] != '']}"
    )
    print("")
    print("")

# Set volume threshold for func/bold acquisitions
setVolumeThreshold(dataset_list_unique_series, objects_list)

# Extract important series information to display in ezBIDS UI
ui_series_info_list = extract_series_info(dataset_list_unique_series)

# Convert information to dictionary
EZBIDS = {
    "readme": readme,
    "datasetDescription": dataset_description_dic,
    "subjects": subjects_information,
    "participantsColumn": participants_column_info,
    "participantsInfo": participants_info,
    "series": ui_series_info_list,
    "objects": objects_list
}

# Write dictionary to ezBIDS_core.json
with open("ezBIDS_core.json", "w") as fp:
    json.dump(EZBIDS, fp, indent=3)

print(f"--- Analyzer completion time: {time.time() - start_time} seconds ---")
