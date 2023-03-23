"""Oriented Bounding Box Annotations.

Provides a toolkit to work with oriented bounding box ann_info.

Author:
    Yvan Satyawan <y_satyawan@hotmail.com>
    Lukas Tuggener <tugg@zhaw.ch>

Created on:
    February 19, 2020
"""
import json
from time import time
from datetime import datetime
from typing import List

import numpy as np
import os.path as osp
from PIL import Image, ImageColor, ImageDraw, ImageFont
import colorcet as cc
import pandas as pd
from tqdm import tqdm
try:
    from .polyiou import iou_poly, VectorDouble
except ModuleNotFoundError:
    import warnings
    warning_string = 'polyiou was not found. Running with no support for ' \
                     'metric calculations.'
    warnings.warn(warning_string)


class OBBAnns:
    def __init__(self,
                 ann_file):
        """Toolkit to work with Oriented Bounding Boxes.

        Workflow is generally to initialize the class, load ann_info, run the
        training loop, then load proposals generated by the network, and finally
        to calculate the various metrics.

        Provides the following methods:
        - load_annotations(): Loads annotations to memory.
        - load_proposals(): Loads given proposals to memory.
        - set_annotation_set_filter(): Applies a filter by annotation set.
        - get_imgs(): Gets desired image information.
        - get_anns(): Gets annotation information for a given image.
        - get_cats(): Gets all cats in the dataset.
        - get_ann_ids(): Gets annotation information by annotation ID.
        - get_img_ann_pairs(): Gets image-annotation pairs by image.
        - get_img_props(): Gets proposasls that belong to a given image.
        - calculate_metrics(): Calculate validation metrics from proposals.
        - visualize_anns(): Visualizes annotations for an image using Pillow.

        :param ann_file: Path to the annotation file.
        :type ann_file: str
        """
        # Store class attributes
        self.ann_file = ann_file

        self.proposal_file = None
        self.proposals = None
        self.props_oriented = False
        self.prop_ann_set_idx = None
        self.dataset_info = None
        self.img_info = None
        self.img_idx_lookup = dict()
        self.annotation_sets = None
        self.cat_info = None
        self.ann_info = None
        self.chosen_ann_set = None  # type: None or List[str]
        self.classes_blacklist = []
        self.classes_blacklist_id = []

    def __repr__(self):
        information = "<Oriented Bounding Box Dataset>\n"
        information += f"Ann file: {self.ann_file}\n"
        if self.dataset_info is not None:
            information += f"Num images: {len(self.img_info)}\n"
            information += f"Num anns: {len(self.ann_info)}\n"
            information += f"Num cats: {len(self.cat_info)}"
        else:
            information += "Annotations not yet loaded\n"
        if self.proposal_file:
            information += f"\nProposal file: {self.proposal_file}"
            information += f"\nNum proposals: {len(self.proposals)}>"
        else:
            information += "\nNo proposals loaded."
        return information

    def __len__(self):
        return 0 if self.img_info is None else len(self.img_info)

    @staticmethod
    def _xor_args(m, n):
        only_one_arg = ((m is not None and n is None)
                        or (m is None and n is not None))
        assert only_one_arg, 'Only one type of request can be done at a time'

    def load_annotations(self, annotation_set_filter=None):
        """Loads ann_info into memory.

        This is not done in the init in case a dataset is just to be initialized
        without actually loading it into memory yet.

        :param annotation_set_filter: Set a filter so that future calls to
            methods which get annotations only returns a specific annotation
            sets. If None is given, then the all annotation sets are returned.
            Annotation sets can also be chosen each time a method which gets
            annotations is called.
        :type annotation_set_filter: str
        """
        print('loading ann_info...')

        # Set up timer
        start_time = time()
        with open(self.ann_file, 'r') as ann_file:
            data = json.load(ann_file)

        self.dataset_info = data['info']
        self.annotation_sets = data['annotation_sets']

        # Sets annotation sets and makes sure it exists
        if annotation_set_filter is not None:
            assert annotation_set_filter in self.annotation_sets, \
                f"The chosen annotation_set_filter " \
                f"{annotation_set_filter} is not a in the available " \
                f"annotations sets."
            self.chosen_ann_set = annotation_set_filter
        else:
            self.chosen_ann_set = self.annotation_sets

        self.cat_info = {int(k): v for k, v in data['categories'].items()}

        # Process annnotations
        ann_id = []
        anns = {'a_bbox': [],
                'o_bbox': [],
                'cat_id': [],
                'area': [],
                'img_id': [],
                'comments': []}

        for k, v in data['annotations'].items():
            ann_id.append(int(k))
            anns['a_bbox'].append(v['a_bbox'])
            anns['o_bbox'].append(v['o_bbox'])
            anns['cat_id'].append(v['cat_id'])
            anns['area'].append(v['area'])
            anns['img_id'].append(v['img_id'])
            anns['comments'].append(v['comments'])
        self.ann_info = pd.DataFrame(anns, ann_id)

        self.img_info = data['images']

        for i, img in enumerate(data['images']):
            # lookup table used to figure out the index in self.img_info of
            # every image based on their img_id
            self.img_idx_lookup[int(img['id'])] = i

        self.img_info = data['images']

        print("done! t={:.2f}s".format(time() - start_time))

    def load_proposals(self, proposal_file):
        """Loads proposals into memory.

        This loads the generated proposals into memory so that metrics can be
        calculated on them.

        :param proposal_file: Path to the generated proposals file.
        :type proposal_file: str
        """
        assert self.img_info is not None, 'Annotations must be loaded before ' \
                                          'proposals'
        self.proposal_file = proposal_file
        print('loading proposals...')
        start_time = time()
        with open(proposal_file, 'r') as p_file:
            props = json.load(p_file)

        # Get the index of the proposed annotation set so the right cat is
        # chosen as the GT set.
        self.prop_ann_set_idx = self.annotation_sets.index(
            props['annotation_set']
        )

        props_dict = {
            'bbox': [],
            'cat_id': [],
            'img_idx': [],
            'score': []
        }
        bbox_len = len(props['proposals'][0]['bbox'])
        assert bbox_len in (4, 8), 'bbox proposal is malformed. \'bbox\' ' \
                                   'must have a length of 4 or 8.'
        if bbox_len == 8:
            self.props_oriented = True

        for prop in props['proposals']:
            prop_img_idx = self.img_idx_lookup[prop["img_id"]]
            props_dict['bbox'].append(np.asarray(prop['bbox'],
                                                 dtype=np.float32))
            props_dict['cat_id'].append(prop['cat_id'])
            props_dict['img_idx'].append(prop_img_idx)
            props_dict['score'].append(prop['score'])

        self.proposals = pd.DataFrame(props_dict)

        print('done! t={:.2f}s'.format(time() - start_time))

    def set_annotation_set_filter(self, annotation_set_filter: List[str]):
        """Sets the annotation set filter for future get calls.

        :param annotation_set_filter: The annotation set to filter by.
        :type annotation_set_filter: str
        """
        self.chosen_ann_set = annotation_set_filter

    def set_class_blacklist(self, blacklist):
        """Sets the annotation set filter for future get calls.

        :param blacklist: a list of classnames to be ignored
        :type blacklist: list
        """
        self.classes_blacklist = blacklist
        self.classes_blacklist_id = [key
                                     for (key, value) in self.cat_info.items()
                                     if value['name'] in self.classes_blacklist]

    def get_imgs(self, idxs=None, ids=None):
        """Gets the information of imgs at the given indices/ids.

        This only works with either idxs or ids, i.e. cannot get both the given
        idxs AND the given ids.

        :param idxs: The indices of the desired images.
        :param ids: The ids of the desired images.
        :type idxs: list or tuple
        :type ids: list or tuple
        :returns: The information of the requested images as a list. Filenames
            will have had the data root as well as paths added to them.
        :rtype: list
        :raises: AssertionError if both idxs and ids are given.
        """
        self._xor_args(idxs, ids)

        if idxs is not None:
            assert isinstance(idxs, list), 'Given indices idxs must be a ' \
                                           'list or tuple'

            return [self.img_info[idx] for idx in idxs]
        else:
            assert isinstance(ids, list), 'Given ids must be a list or tuple'
            return [self.img_info[self.img_idx_lookup[i]] for i in ids]

    def get_anns(self, img_idx=None, img_id=None, ann_set_filter=None):
        """Gets the annotations for a given image by idx or img_id.

        :param img_idx: The index of the image.
        :param img_id: The img_id of the image.
        :param ann_set_filter: Filter by annotation set. If None, uses the
            filter chosen in the method set_annotation_filter().
        :type img_idx: int
        :type img_id: int
        :type ann_set_filter: str
        :returns: Annotation information (dict) for that image with the key
            being the annotation ID and the value being the annotation
            information.
        :rtype: pd.DataFrame
        """
        self._xor_args(img_idx, img_id)

        if img_idx is not None:
            return self.get_ann_ids(self.img_info[img_idx]['ann_ids'],
                                    ann_set_filter)
        else:
            ann_ids = self.img_info[self.img_idx_lookup[img_id]]['ann_ids']
            return self.get_ann_ids(ann_ids, ann_set_filter)

    def get_cats(self):
        """Just returns the self.cat_info dictionary.

        :returns The category information of the currently loaded dataset.
        :rtype: dict
        """
        return {key: value for (key, value) in self.cat_info.items()
                if value['annotation_set'] in self.chosen_ann_set
                and value['name'] not in self.classes_blacklist}

    def get_ann_ids(self, ann_ids, ann_set_filter=None):
        """Gets the annotation information for a given list of ann_ids.

        :param ann_ids: The annotation ids that are desired.
        :param ann_set_filter: Filter by annotation set. If None, uses the
            filter chosen in the method set_annotation_filter().
        :type ann_ids: list[str] or list[int]
        :type ann_set_filter: list or str
        :returns: The annotation information requested.
        :rtype: pd.DataFrame
        """
        assert isinstance(ann_ids, list), 'Given ann_ids must be a list or ' \
                                          'tuple'

        ann_ids = [int(i) for i in ann_ids]
        selected = self.ann_info.loc[ann_ids]

        # Get annotation set index and return only the specific category id
        if ann_set_filter is None:
            ann_set_filter = self.chosen_ann_set
        if isinstance(ann_set_filter, str):
            ann_set_filter = [ann_set_filter]
        ann_set_idx = [self.annotation_sets.index(ann_set)
                       for ann_set in ann_set_filter]

        def filter_ids(record):
            return [int(record[idx])
                    for idx in ann_set_idx
                    if int(record[idx]) not in self.classes_blacklist_id]

        selected['cat_id'] = selected['cat_id'].map(filter_ids)
        selected = selected[selected['cat_id'].map(lambda x: len(x)) > 0]

        return selected

    def get_img_ann_pair(self, idxs=None, ids=None, ann_set_filter=None):
        """Gets the information and annotations at the given indices/ids.

        This only works with either idxs or ids, i.e. cannot get both the given
        idxs AND the given ids.

        :param idxs: The indices of the desired images.
        :param ids: The ids of the desired images.
        :param ann_set_filter: Filter by annotation set. If None, uses the
            filter chosen in the method set_annotation_filter().
        :type idxs: list or tuple
        :type ids: list or tuple
        :type ann_set_filter: list or str
        :returns: The information of the requested images as a tuple (list of
            image info, corresponding annotations)
        :rtype: tuple
        :raises: AssertionError if both idxs and ids are given.
        """
        self._xor_args(idxs, ids)

        imgs = self.get_imgs(idxs, ids)
        anns = [self.get_ann_ids(img['ann_ids'], ann_set_filter)
                for img in imgs]

        return imgs, anns

    def get_img_props(self, idxs=None, ids=None):
        """Gets the proposals of an image at a given index or with a given ID.

        :param idxs: The indices of the desired images.
        :param ids: The ids of the desired images
        :type idxs: list or tuple
        :type ids: list or tuple
        :returns: The information of the requested images as a tuple (list of
            image info, corresponding annotations)
        :rtype: pd.DataFrame
        :raises: AssertionError if both idxs and ids are given.
        """
        self._xor_args(idxs, ids)

        # Proposals are checked by idx, not by id so we need to find their idxs
        if ids is not None:
            idxs = [self.img_idx_lookup[img_id] for img_id in ids]

        selector = self.proposals.img_idx.isin(idxs)
        return self.proposals[selector]

    def calculate_metrics(self, iou_thrs=(0.5, 0.55), classwise=False,
                          average_thrs=True):
        """Calculates proposed bounding box validation metrics.

        Calculates accuracy as total true positives / total detections
        Calculates the AP with IoU = .50. Will return a mean AP as well
        as a class-wise AP.
        Calculates the AR with 100 detections per image.

        :param list iou_thrs: IOU threshold range to calculate. Two values
            should be given. IOU is then calculated for each threshold value in
            the given range.
        :param bool classwise: Whether or not to use calculate classwise-
            metrics. If False, uses calculates average metrics.
        :param bool average_thrs: Whether or not to get the average of the
            thresholds range.

        :returns A dictionary of calculated metric values.
        :rtype: dict
        """

        def calculate_tpfp(detection, img_gt):
            """Calculates whether a detection is a true or false positive.

            :param pd.Series detection: Data frame for the detection
            :param pd.DataFrame img_gt: Ground truth for the image.
            :returns: ann_id as int of true positive bbox. If the detection is a
                false positive, then returns -1. Also returns the overlap as a
                float with the true positive bbox. Keys are 'bbox'_id' and
                'overlap'.
            :rtype: dict
            """
            def calculate_oriented_overlap(row):
                return iou_poly(VectorDouble(row['gt']),
                                VectorDouble(row['det']))

            def calculate_aligned_overlap(row):
                a = row['gt']
                b = row['det']
                dx_int = min([a[2], b[2]]) - max([a[0], b[0]])
                dy_int = min([a[3], b[3]]) - max([a[1], b[1]])

                dx_ov = max([a[2], b[2]]) - min([a[0], b[0]])
                dy_ov = max([a[3], b[3]]) - min([a[1], b[1]])

                if (dx_int >= 0) and (dy_int >= 0):
                    return (dx_int * dy_int) / (dx_ov * dy_ov)
                else:
                    return 0.

            # expect to only have one annotation set at this point
            gt_cat_id = img_gt['cat_id'].map(lambda x: x[0])
            same_cat_gt = img_gt[gt_cat_id == detection['cat_id']]
            if len(same_cat_gt) > 0:
                if self.props_oriented:
                    df = pd.DataFrame({
                        'gt': same_cat_gt['o_bbox'],
                        'det': [detection['bbox'] * len(same_cat_gt)]
                    })
                    overlaps = df.apply(calculate_oriented_overlap, 1)
                else:
                    df = pd.DataFrame({
                        'gt': same_cat_gt['a_bbox'],
                        'det': [detection['bbox']] * len(same_cat_gt)
                    })
                    # overlaps = np.zeros(df.shape[0])
                    # for id, row in enumerate(df.iterrows()):
                    #     calculate_aligned_overlap(row)
                    #     print(row)
                    overlaps = df.apply(calculate_aligned_overlap, 1)

                max_overlap = overlaps.max()

                if max_overlap > 0.2:  # minimum overlap to "reserve a gt"
                    # Means that there's at least one with an overlap. We take
                    # the object with highest overlap.
                    return {'bbox_id': overlaps.idxmax(),
                            'overlap': max_overlap}
                else:
                    return {'bbox_id': -1, 'overlap': 0.}
            else:
                return {'bbox_id': -1, 'overlap': 0.}

        overlaps = []
        unique_images = np.unique(self.proposals['img_idx'])
        tot_props = self.proposals['cat_id'].value_counts()

        for img_idx in tqdm(unique_images):
            # For every image, look at each detection
            # img_props is a pandas DataFrame
            img_props = self.proposals[self.proposals['img_idx'] == img_idx]
            img_gt = self.get_anns(img_idx=img_idx)  # This is a dict of dicts
            # sort props by confidence
            img_props = img_props.sort_values('score')

            # For all detections in an image, compare them to the ground truths
            for det_idx, det in img_props.iterrows():
                tpfp = calculate_tpfp(det, img_gt)
                val, overlap = tpfp['bbox_id'], tpfp['overlap']
                overlaps.append([val, overlap, det['cat_id'],
                                 float(det['score'])])
                if val != -1:
                    img_gt = img_gt.drop(val)
                    # TODO: compute all overlaps and find best gt/props
                    # matching in a second step
        overlaps = np.array(overlaps)

        results_dict = {}
        if classwise:
            for class_idx in np.unique(overlaps[:, 2]):
                results_dict[class_idx] = self._evaluate_overlaps(
                    overlaps[overlaps[:, 2] == class_idx],
                    iou_thrs,
                    by_class=class_idx
                )
        else:
            results_dict["average"] = self._evaluate_overlaps(
                overlaps,
                tot_props,
                iou_thrs)

        if average_thrs:
            for cls_key, tresh_dict in results_dict.items():
                averaged_dict = {'accuracy': 0,
                                 'precision': 0,
                                 'recall': 0}
                for _, eval_dict in tresh_dict.items():
                    for key in averaged_dict.keys():
                        averaged_dict[key] += eval_dict[key]
                for key in averaged_dict.keys():
                    averaged_dict[key] = averaged_dict[key] / len(tresh_dict)
                results_dict[cls_key] = averaged_dict
        return results_dict

    def _evaluate_overlaps(self, overlaps, iou_thrs, by_class=None):
        metrics = {}

        for iou_thr in iou_thrs:
            
            # sort overlaps by score:
            overlaps = overlaps[overlaps[:, 3].argsort()[::-1]]

            tp = overlaps[:, 1] >= iou_thr
            fp = overlaps[:, 1] < iou_thr

            tp_sum = np.cumsum(tp).astype(dtype=np.float)
            fp_sum = np.cumsum(fp).astype(dtype=np.float)

            # Count number of ground truths without a corresponding detection
            # (False Negative)
            if by_class is not None:
                ann_gt_idxs = set(self.ann_info[
                                      self.ann_info['cat_id'].map(
                                          lambda x: int(x[0])
                                      ) == by_class].index)
            else:
                ann_gt_idxs = set(self.ann_info.index)

            nr_gt = len(ann_gt_idxs)

            if nr_gt > 0:
                recall = tp_sum / nr_gt
            else:
                recall = tp_sum * 0
            precision = tp_sum / (fp_sum + tp_sum + np.spacing(1))

            # pad vectors for computation
            average_precision = self._average_precision(recalls=recall,
                                                        precisions=precision)
            
            metrics[iou_thr] = {'ap': average_precision,
                                'precision': np.average(precision),
                                'recall': np.average(recall)}
        return metrics

    @staticmethod
    def _average_precision(recalls, precisions, mode='area'):
        """Calculate average precision (for single or multiple scales).

        Args:
            recalls (ndarray): shape (num_scales, num_dets) or (num_dets, )
            precisions (ndarray): shape (num_scales, num_dets) or (num_dets, )
            mode (str): 'area' or '11points', 'area' means calculating the area
                under precision-recall curve, '11points' means calculating
                the average precision of recalls at [0, 0.1, ..., 1]

        Returns:
            float or ndarray: calculated average precision
        """
        no_scale = False
        if recalls.ndim == 1:
            no_scale = True
            recalls = recalls[np.newaxis, :]
            precisions = precisions[np.newaxis, :]
        assert recalls.shape == precisions.shape and recalls.ndim == 2
        num_scales = recalls.shape[0]
        ap = np.zeros(num_scales, dtype=np.float32)
        if mode == 'area':
            zeros = np.zeros((num_scales, 1), dtype=recalls.dtype)
            ones = np.ones((num_scales, 1), dtype=recalls.dtype)
            mrec = np.hstack((zeros, recalls, ones))
            mpre = np.hstack((zeros, precisions, zeros))
            for i in range(mpre.shape[1] - 1, 0, -1):
                mpre[:, i - 1] = np.maximum(mpre[:, i - 1], mpre[:, i])
            for i in range(num_scales):
                ind = np.where(mrec[i, 1:] != mrec[i, :-1])[0]
                ap[i] = np.sum(
                    (mrec[i, ind + 1] - mrec[i, ind]) * mpre[i, ind + 1])
        elif mode == '11points':
            for i in range(num_scales):
                for thr in np.arange(0, 1 + 1e-3, 0.1):
                    precs = precisions[i, recalls[i, :] >= thr]
                    prec = precs.max() if precs.size > 0 else 0
                    ap[i] += prec
                ap /= 11
        else:
            raise ValueError(
                'Unrecognized mode, only "area" and "11points" are supported')
        if no_scale:
            ap = ap[0]
        return ap

    def _draw_bbox(self, draw, ann, color, oriented, annotation_set=None,
                   print_label=False, print_staff_pos=False, print_onset=False,
                   instances=False):

        """Draws the bounding box onto an image with a given color.

        :param ImageDraw.ImageDraw draw: ImageDraw object to draw with.
        :param dict ann: Annotation information dictionary of the current
            bounding box to draw.
        :param str color: Color to draw the bounding box in as a hex string,
            e.g. '#00ff00'
        :param bool oriented: Choose between drawing oriented or aligned
            bounding box.
        :param Optional[int] annotation_set: Index of the annotation set to be
            drawn. If None is given, the first one available will be drawn.
        :param Optional[bool] print_label: Determines if the class labels
        are printed on the visualization
        :param Optional[bool] print_staff_pos: Determines if the staff positions
        are printed on the visualization
        :param Optional[bool] print_onset:  Determines if the onsets are
        printed on the visualization

        :return: The drawn object.
        :rtype: ImageDraw.ImageDraw
        """
        annotation_set = 0 if annotation_set is None else annotation_set
        cat_id = ann['cat_id']
        if isinstance(cat_id, list):
            cat_id = int(cat_id[annotation_set])

        parsed_comments = self.parse_comments(ann['comments'])

        if oriented:
            bbox = ann['o_bbox']
            draw.line(bbox + bbox[:2], fill=color, width=3
                      )
        else:
            bbox = ann['a_bbox']
            draw.rectangle(bbox, outline=color, width=2)

        # Now draw the label below the bbox
        x0 = min(bbox[::2])
        y0 = max(bbox[1::2])
        pos = (x0, y0)

        def print_text_label(position, text, color_text, color_box):
            x1, y1 = ImageFont.load_default().getsize(text)
            x1 += position[0] + 4
            y1 += position[1] + 4
            draw.rectangle((position[0], position[1], x1, y1), fill=color_box)
            draw.text((position[0] + 2, position[1] + 2), text, color_text)
            return x1, position[1]

        if instances:
            label = str(int(parsed_comments['instance'].lstrip('#'), 16))
            print_text_label(pos, label, '#ffffff', '#303030')

        else:
            label = self.cat_info[cat_id]['name']

            if print_label:
                pos = print_text_label(pos, label, '#ffffff', '#303030')
            if print_onset and 'onset' in parsed_comments.keys():
                pos = print_text_label(pos, parsed_comments['onset'], '#ffffff',
                                       '#091e94')
            if print_staff_pos and 'rel_position' in parsed_comments.keys():
                print_text_label(pos, parsed_comments['rel_position'],
                                 '#ffffff', '#0a7313')

        return draw

    def get_class_occurences(self):
        """Just returns the number of occurences per category.

        :returns The number of occurences per category in the currently loaded
            dataset.
        :rtype: dict
        """
        annotation_set_index = self.annotation_sets.index(
            self.chosen_ann_set[0]
        )
        anns = self.ann_info['cat_id'].apply(lambda x: x[annotation_set_index])
        anns_count = anns.value_counts()
        return_dict = {}
        for (key, value) in self.cat_info.items():
            if value['annotation_set'] not in self.chosen_ann_set \
                    or value['name'] in self.classes_blacklist:
                continue

            if str(key) in anns_count.index:
                return_dict[value['name']] = anns_count[str(key)]
            else:
                return_dict[value['name']] = 0

        return return_dict

    @staticmethod
    def parse_comments(comment):
        """Parses the comment field of an annotation.

        :returns dictionary with every comment name as keys
        :rtype: dict
        """
        parsed_dict = dict()
        for co in comment.split(";"):
            if len(co.split(":")) > 1:
                key, value = co.split(":")
                parsed_dict[key] = value
        return parsed_dict

    def visualize(self,
                  img_idx=None,
                  img_id=None,
                  data_root=None,
                  out_dir=None,
                  annotation_set=None,
                  oriented=True,
                  instances=False,
                  show=True):
        """Uses PIL to visualize the ground truth labels of a given image.

        img_idx and img_id are mutually exclusive. Only one can be used at a
        time. If proposals are currently loaded, then also visualizes the
        proposals.

        :param int img_idx: The index of the desired image.
        :param int img_id: The id of the desired image.
        :param Optional[str] data_root: Path to the root data directory. If
            none is given, it is assumed to be the parent directory of the
            ann_file path.
        :param Optional[str] out_dir: Directory to save the visualizations in.
            If a directory is given, then the visualizations produced will also
            be saved.
        :param Optional[str] annotation_set: The annotation set to be
            visualized. If None is given, then the first annotation set
            available will be visualized.
        :param Optional[bool] oriented: Whether to show aligned or oriented
            bounding boxes. A value of True means it will show oriented boxes.
        :param bool show: Whether or not to use pillow's show() method to
            visualize the image.
        :param bool instances: Choose whether to show classes or instances. If
            False, then shows classes. Else, shows instances as the labels on
            bounding boxes.
        """
        # Since we can only visualize a single image at a time, we do i[0] so
        # that we don't have to deal with lists. get_img_ann_pair() returns a
        # tuple that's why we use list comprehension
        img_idx = [img_idx] if img_idx is not None else None
        img_id = [img_id] if img_id is not None else None

        if annotation_set is None:
            annotation_set = 0
            self.chosen_ann_set = self.annotation_sets[0]
        else:
            annotation_set = self.annotation_sets.index(annotation_set)
            self.chosen_ann_set = self.chosen_ann_set[annotation_set]

        img_info, ann_info = [i[0] for i in
                              self.get_img_ann_pair(
                                  idxs=img_idx, ids=img_id)]

        # Get the data_root from the ann_file path if it doesn't exist
        if data_root is None:
            data_root = osp.split(self.ann_file)[0]

        img_dir = osp.join(data_root, 'images')
        seg_dir = osp.join(data_root, 'segmentation')
        inst_dir = osp.join(data_root, 'instance')

        # Get the actual image filepath and the segmentation filepath
        img_fp = osp.join(img_dir, img_info['filename'])
        print(f'Visualizing {img_fp}...')

        # Remember: PIL Images are in form (h, w, 3)
        img = Image.open(img_fp)

        if instances:
            # Do stuff
            inst_fp = osp.join(
                inst_dir,
                osp.splitext(img_info['filename'])[0] + '_inst.png'
            )
            overlay = Image.open(inst_fp)
            img.putalpha(255)
            img = Image.alpha_composite(img, overlay)
            img = img.convert('RGB')

        else:
            seg_fp = osp.join(
                seg_dir,
                osp.splitext(img_info['filename'])[0] + '_seg.png'
            )
            overlay = Image.open(seg_fp)

            # Here we overlay the segmentation on the original image using the
            # colorcet colors
            # First we need to get the new color values from colorcet
            colors = [ImageColor.getrgb(i) for i in cc.glasbey]
            colors = np.array(colors).reshape(768, ).tolist()
            colors[0:3] = [0, 0, 0]  # Set background to black

            # Then put the palette
            overlay.putpalette(colors)
            overlay_array = np.array(overlay)

            # Now the img and the segmentation can be composed together. Black
            # areas in the segmentation (i.e. background) are ignored

            mask = np.zeros_like(overlay_array)
            mask[np.where(overlay_array == 0)] = 255
            mask = Image.fromarray(mask, mode='L')

            img = Image.composite(img, overlay.convert('RGB'), mask)
        draw = ImageDraw.Draw(img)

        # Now draw the gt bounding boxes onto the image
        for ann in ann_info.to_dict('records'):
            draw = self._draw_bbox(draw, ann, '#ed0707', oriented,
                                   annotation_set, instances)

        if self.proposals is not None:
            prop_info = self.get_img_props(idxs=img_idx, ids=img_id)

            for prop in prop_info.to_dict('records'):
                prop_oriented = len(prop['bbox']) == 8
                draw = self._draw_bbox(draw, prop, '#ff0000', prop_oriented)

        if show:
            img.show()
        if out_dir is not None:
            img.save(osp.join(out_dir, datetime.now().strftime('%m-%d_%H%M%S'))
                     + '.png')